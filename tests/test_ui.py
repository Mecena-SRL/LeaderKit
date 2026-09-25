"""Smoke test del pannello con un UIManager finto: costruzione, eventi, generazione."""

import fake_resolve as fr
from leaderkit import ui as lk_ui


class Widget(object):
    def __init__(self, kind, props, children=None):
        self.kind = kind
        self.children = children or []
        self.__dict__.update({"Text": "", "Checked": False, "Value": 1, "CurrentIndex": -1,
                              "Enabled": True, "PlainText": "", "_items": []})
        self.__dict__.update(props)

    def AddItems(self, items):
        self._items += list(items)
        if self.CurrentIndex < 0 and self._items:
            self.CurrentIndex = 0

    def Clear(self):
        self._items = []
        self.CurrentIndex = -1

    @property
    def CurrentText(self):
        return self._items[self.CurrentIndex] if 0 <= self.CurrentIndex < len(self._items) else ""


class UI(object):
    def __getattr__(self, kind):
        def make(props=None, children=None):
            if isinstance(props, list):
                props, children = {}, props
            return Widget(kind, props or {}, children)
        return make


class Handlers(object):
    def __init__(self):
        self.__dict__["_ns"] = {}

    def __getattr__(self, name):
        return self._ns.setdefault(name, type("H", (), {})())


class Window(object):
    def __init__(self, root):
        self.root = root
        self.On = Handlers()

    def GetItems(self):
        out = {}
        stack = [self.root]
        while stack:
            w = stack.pop()
            if hasattr(w, "ID"):
                out[w.ID] = w
            stack.extend(w.children)
        return out

    def Show(self):
        pass

    def Hide(self):
        pass


class Dispatcher(object):
    def __init__(self, ui):
        self.window = None

    def AddWindow(self, props, children):
        self.window = Window(Widget("Window", props, children))
        return self.window

    def RunLoop(self):
        pass

    def ExitLoop(self):
        pass


class Bmd(object):
    def __init__(self):
        self.disp = None

    def UIDispatcher(self, ui):
        self.disp = Dispatcher(ui)
        return self.disp


class Fusion(object):
    UIManager = UI()


def test_panel_generates(tmp_path, monkeypatch):
    monkeypatch.setenv("LEADERKIT_CACHE", str(tmp_path / "cache"))
    monkeypatch.setattr(lk_ui.paths, "settings_file", lambda: str(tmp_path / "v.json"))
    project = fr.Project("25", False, 3840, 2160)
    project.new_program_timeline("Film", 40)
    bmd = Bmd()
    lk_ui.main(fr.Resolve(project), Fusion(), bmd)
    win = bmd.disp.window
    items = win.GetItems()
    assert "25 fps, 3840 × 2160" in items["Info"].Text
    names = items["Preset"]._items
    items["Preset"].CurrentIndex = names.index("Cinema / DCP")
    win.On.Preset.CurrentIndexChanged(None)
    assert items["Markers"].Checked and items["MarkerEvery"].Text == "20m"
    items["S_title"].Text = "Film di prova"
    win.On.Generate.Clicked(None)
    assert "ERRORE" not in items["Log"].PlainText, items["Log"].PlainText
    assert "FFOA: 01:00:08:00" in items["Log"].PlainText
    assert project.current.name.startswith("Film — LeaderKit")
    win.On.Remove.Clicked(None)
    assert "Rimossi" in items["Log"].PlainText
    assert (tmp_path / "v.json").exists()
