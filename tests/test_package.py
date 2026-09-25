"""Installa il pacchetto zip in una HOME temporanea ed esegue lo script
d'ingresso come farebbe Resolve (globali ``resolve``/``fusion``/``bmd``)."""

import os
import subprocess
import sys
import zipfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

pytestmark = pytest.mark.skipif(not sys.platform.startswith("linux"),
                                reason="installer testato su Linux")


def test_install_and_run(tmp_path):
    subprocess.check_call([sys.executable, os.path.join(ROOT, "tools", "build.py")],
                          stdout=subprocess.DEVNULL)
    from leaderkit import __version__
    with zipfile.ZipFile(os.path.join(ROOT, "dist", "LeaderKit-%s.zip" % __version__)) as zf:
        zf.extractall(str(tmp_path / "pkg"))
    script = tmp_path / "pkg" / "LeaderKit" / "install.sh"
    os.chmod(str(script), 0o755)
    home = tmp_path / "home"
    home.mkdir()
    env = dict(os.environ, HOME=str(home), LEADERKIT_NO_PAUSE="1")
    subprocess.check_call(["bash", str(script)], env=env, stdout=subprocess.DEVNULL)
    fusion_dir = home / ".local" / "share" / "DaVinciResolve" / "Fusion"
    entry = fusion_dir / "Scripts" / "Utility" / "LeaderKit.py"
    assert entry.exists()
    assert (fusion_dir / "Templates" / "LeaderKit.drfx").exists()
    assert (fusion_dir / "LeaderKit" / "presets" / "cinema_dcp.json").exists()

    # Esecuzione in un processo pulito: la libreria deve arrivare dall'installazione.
    runner = (
        "import sys; sys.path.insert(0, %r); sys.path.insert(0, %r)\n"
        "import fake_resolve as fr\n"
        "p = fr.Project('24', False, 1920, 1080)\n"
        "p.new_program_timeline('Rullo 1', 30)\n"
        "g = {'resolve': fr.Resolve(p), 'fusion': None, 'bmd': None, '__file__': %r}\n"
        "exec(compile(open(%r).read(), %r, 'exec'), g)\n"
        "import leaderkit; assert leaderkit.__file__.startswith(%r), leaderkit.__file__\n"
        "print(p.current.name, p.current.GetStartTimecode())\n"
    ) % (os.path.join(ROOT, "tests"), str(fusion_dir / "LeaderKit"), str(entry), str(entry), str(entry), str(fusion_dir))
    env["LEADERKIT_CACHE"] = str(tmp_path / "cache")
    env["PYTHONPATH"] = ""
    out = subprocess.check_output([sys.executable, "-c", runner], env=env,
                                  cwd=str(tmp_path)).decode()
    assert "Rullo 1 — LeaderKit Cinema / DCP 00:59:50:00" in out

    subprocess.check_call(["bash", str(script), "--uninstall"], env=env,
                          stdout=subprocess.DEVNULL)
    assert not entry.exists()
