import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import venv


REPOSITORY = Path(__file__).resolve().parents[1]
INSTALL_PACKAGES = """
import os
from pathlib import Path
import sys
import sysconfig

if os.environ.get('FAIL_INSTALL'):
    sys.exit(1)
site = Path(sysconfig.get_path('purelib'))
for name in ('yaml', 'rich'):
    (site / (name + '.py')).write_text('')
Path(os.environ['INSTALL_LOG']).write_text(sys.executable + '\\n' + str(Path.cwd()))
"""
PIP_MODULE = """
import sys

if sys.argv[1:] == ['--version']:
    sys.exit(0)
""" + INSTALL_PACKAGES


class PythonStartupTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="k8squest startup ")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.project = self.root / "project"
        (self.project / "engine").mkdir(parents=True)
        for name in ("play.sh", "install.sh", "requirements.txt", "engine/python_env.sh"):
            shutil.copy(REPOSITORY / name, self.project / name)
        (self.project / "engine/engine.py").write_text(
            "import sys, yaml, rich\nprint('ENGINE_READY', sys.executable)\n"
        )
        venv.EnvBuilder(with_pip=False).create(self.project / "venv")
        self.python = self.project / "venv/bin/python3"
        self.site = Path(subprocess.check_output(
            [str(self.python), "-c", "import sysconfig; print(sysconfig.get_path('purelib'))"],
            text=True,
        ).strip())
        self.bin = self.root / "bin"
        self.bin.mkdir()
        for name in ("dirname", "grep"):
            (self.bin / name).symlink_to(shutil.which(name))
        (self.bin / "python3").symlink_to(sys.executable)
        self.env = os.environ.copy()
        for name in ("CONDA_PREFIX", "VIRTUAL_ENV", "PYTHONPATH", "PYTHONHOME"):
            self.env.pop(name, None)
        self.env.update(
            PATH=str(self.bin),
            PYTHONPATH=str(self.site),
            K8S_CLUSTER_TYPE="k3s",
            KUBECONFIG=str(self.root / "kubeconfig"),
            INSTALL_LOG=str(self.root / "installed"),
            CLUSTER_LOG=str(self.root / "cluster"),
        )
        for name in ("jq", "kubectl", "kind", "systemctl"):
            self.write_command(name, (
                '#!/bin/bash\nprintf "%s\\n" "$0 $*" >> "$CLUSTER_LOG"\n'
                + ("exit 1\n" if name == "systemctl" else "printf 'k8squest\\n'\n")
            ))

    def write_command(self, name, content):
        path = self.bin / name
        path.write_text(content)
        path.chmod(0o755)

    def run_script(self, name="play.sh"):
        return subprocess.run(
            ["/bin/bash", str(self.project / name)],
            cwd=self.root,
            env=self.env,
            capture_output=True,
            text=True,
            timeout=20,
        )

    def assert_game_started(self, result):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("ENGINE_READY", result.stdout)

    def test_missing_dependencies_are_installed_into_the_engine_environment(self):
        (self.site / "pip.py").write_text(PIP_MODULE)
        self.env["VIRTUAL_ENV"] = str(self.project / "venv")
        result = self.run_script()
        self.assert_game_started(result)
        self.assertEqual(
            (self.root / "installed").read_text(),
            str(self.python) + "\n" + str(self.project),
        )

    def test_ready_environment_starts_without_installing_packages(self):
        for name in ("yaml", "rich"):
            (self.site / (name + ".py")).write_text("")
        self.env["FAIL_INSTALL"] = "1"
        self.assert_game_started(self.run_script())
        self.assertFalse((self.root / "installed").exists())

    def test_failed_install_stops_before_cluster_commands(self):
        (self.site / "pip.py").write_text(PIP_MODULE)
        self.env["FAIL_INSTALL"] = "1"
        result = self.run_script()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Python dependency setup failed", result.stdout)
        self.assertNotIn("ENGINE_READY", result.stdout)
        self.assertFalse((self.root / "cluster").exists())

    def test_missing_pip_is_bootstrapped_when_ensurepip_is_available(self):
        (self.site / "ensurepip.py").write_text(
            "from pathlib import Path\n"
            "if __name__ == '__main__':\n"
            f"    Path(__file__).with_name('pip.py').write_text({PIP_MODULE!r})\n"
        )
        self.assert_game_started(self.run_script())
        self.assertTrue((self.root / "installed").exists())

    def test_uv_repairs_an_environment_without_pip_or_ensurepip(self):
        (self.site / "ensurepip.py").write_text("raise ImportError('ensurepip unavailable')\n")
        self.write_command("uv", (
            f"#!{sys.executable}\nimport subprocess, sys\n"
            "python = sys.argv[sys.argv.index('--python') + 1]\n"
            f"sys.exit(subprocess.call([python, '-c', {INSTALL_PACKAGES!r}]))\n"
        ))
        self.assert_game_started(self.run_script())
        self.assertTrue((self.root / "installed").exists())

    def test_no_installer_stops_with_recovery_instructions_before_cluster_commands(self):
        (self.site / "ensurepip.py").write_text("raise ImportError('ensurepip unavailable')\n")
        result = self.run_script()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("python3-venv", result.stdout)
        self.assertFalse((self.root / "cluster").exists())

    def test_install_uses_project_python_when_run_from_another_directory(self):
        (self.site / "pip.py").write_text(PIP_MODULE)
        self.write_command("pip", "#!/bin/bash\nexit 99\n")
        result = self.run_script("install.sh")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(
            (self.root / "installed").read_text(),
            str(self.python) + "\n" + str(self.project),
        )


if __name__ == "__main__":
    unittest.main()
