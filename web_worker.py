from __future__ import annotations

import argparse
from pathlib import Path

import app_base
from graph_model import OAGraph


class AutosaveOAGraph(OAGraph):
    """OAGraph variant that mirrors accepted changes for the web preview."""

    def __init__(self, model_path: Path) -> None:
        super().__init__()
        self._web_model_path = Path(model_path)
        self._persist()

    def _persist(self) -> None:
        self.save(str(self._web_model_path))

    def add_node(self, *args, **kwargs):
        result = super().add_node(*args, **kwargs)
        if result[0]:
            self._persist()
        return result

    def update_node_attributes(self, *args, **kwargs):
        result = super().update_node_attributes(*args, **kwargs)
        if result:
            self._persist()
        return result

    def add_relation(self, *args, **kwargs):
        result = super().add_relation(*args, **kwargs)
        if result[0]:
            self._persist()
        return result

    def add_characteristic(self, *args, **kwargs):
        result = super().add_characteristic(*args, **kwargs)
        if result[0]:
            self._persist()
        return result

    def add_exchange_characteristic(self, *args, **kwargs):
        result = super().add_exchange_characteristic(*args, **kwargs)
        if result[0]:
            self._persist()
        return result

    def undo(self) -> bool:
        changed = super().undo()
        if changed:
            self._persist()
        return changed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-path", required=True)
    args = parser.parse_args()
    model_path = Path(args.model_path).resolve()

    # app_base creates the graph in OAApp.__init__. Rebinding the factory keeps
    # every existing flow and validation rule while adding live persistence.
    app_base.OAGraph = lambda: AutosaveOAGraph(model_path)  # type: ignore[assignment]

    import app

    app.OAApp().run()


if __name__ == "__main__":
    main()
