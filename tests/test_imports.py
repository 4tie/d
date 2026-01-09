import importlib
import unittest


class ImportTests(unittest.TestCase):
    def test_import_main(self) -> None:
        importlib.import_module("main")

    def test_import_modules(self) -> None:
        importlib.import_module("api.client")
        importlib.import_module("core.strategy_service")
        importlib.import_module("utils.knowledge_base")
        importlib.import_module("utils.ollama_client")
        importlib.import_module("utils.performance_store")


if __name__ == "__main__":
    unittest.main()
