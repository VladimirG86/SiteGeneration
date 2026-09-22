"""Добавляем корень sitegen в sys.path, чтобы тесты импортировали модули напрямую."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
