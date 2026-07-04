from __future__ import annotations

import json
from pathlib import Path

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QApplication, QFileDialog
from qfluentwidgets import ComboBox, PushButton, SettingCard
from qfluentwidgets.common.config import ConfigItem, qconfig


class ApiKeyComboSettingCard(SettingCard):
    """API Key selector with paste/import/clear/delete actions."""

    keyChanged = pyqtSignal(str)

    def __init__(
        self,
        keyConfigItem: ConfigItem,
        keysConfigItem: ConfigItem,
        icon,
        title: str,
        content: str | None = None,
        parent=None,
    ):
        super().__init__(icon, title, content, parent)
        self.keyConfigItem = keyConfigItem
        self.keysConfigItem = keysConfigItem
        self._updating = False

        self.comboBox = ComboBox(self)
        self.comboBox.setMinimumWidth(380)

        self.pasteButton = PushButton(self.tr("粘贴"), self)
        self.importButton = PushButton(self.tr("导入"), self)
        self.clearButton = PushButton(self.tr("清空"), self)
        self.deleteButton = PushButton(self.tr("删除当前"), self)
        for button in (
            self.pasteButton,
            self.importButton,
            self.clearButton,
        ):
            button.setFixedSize(52, 32)
        self.deleteButton.setFixedSize(72, 32)

        self.hBoxLayout.addWidget(self.comboBox, 1, Qt.AlignRight)  # type: ignore
        self.hBoxLayout.addSpacing(12)
        for button in (
            self.pasteButton,
            self.importButton,
            self.clearButton,
            self.deleteButton,
        ):
            self.hBoxLayout.addSpacing(6)
            self.hBoxLayout.addWidget(button)
        self.hBoxLayout.addSpacing(16)

        self._reload_keys()
        self.comboBox.currentTextChanged.connect(self._on_text_changed)
        self.pasteButton.clicked.connect(self._paste_from_clipboard)
        self.importButton.clicked.connect(self._import_from_file)
        self.clearButton.clicked.connect(self._clear_all_keys)
        self.deleteButton.clicked.connect(self._delete_current_key)
        keyConfigItem.valueChanged.connect(self.setValue)

    def _stored_keys(self) -> list[str]:
        raw = qconfig.get(self.keysConfigItem) or "[]"
        try:
            data = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            return []
        if not isinstance(data, list):
            return []
        return self._normalize_keys(data)

    def _normalize_keys(self, values) -> list[str]:
        keys: list[str] = []
        for value in values:
            for key in str(value).replace(",", "\n").split():
                key = key.strip()
                if key:
                    keys.append(key)
        return list(dict.fromkeys(keys))

    def _save_keys(self, keys: list[str]):
        normalized_keys = self._normalize_keys(keys)
        qconfig.set(
            self.keysConfigItem,
            json.dumps(normalized_keys, ensure_ascii=False),
        )

    def _reload_keys(self, selected_key: str | None = None):
        raw_key = (
            qconfig.get(self.keyConfigItem) if selected_key is None else selected_key
        )
        current_key = (raw_key or "").strip()
        keys = self._stored_keys()
        if current_key and current_key not in keys:
            keys.insert(0, current_key)
            self._save_keys(keys)

        self._updating = True
        self.comboBox.clear()
        self.comboBox.addItems(keys)
        self.comboBox.setCurrentText(current_key)
        self._updating = False

    def _add_keys(self, keys: list[str]):
        keys = self._normalize_keys(keys)
        if not keys:
            return
        merged = keys + self._stored_keys()
        self._save_keys(merged)
        self._reload_keys(keys[0])
        self._set_active_key(keys[0])

    def _set_active_key(self, key: str):
        qconfig.set(self.keyConfigItem, key)
        self.keyChanged.emit(key)

    def _on_text_changed(self, text: str):
        if self._updating:
            return
        self._set_active_key(text.strip())

    def setValue(self, value: str):
        value = (value or "").strip()
        if self.comboBox.currentText() == value:
            return
        self._reload_keys(value)

    def _paste_from_clipboard(self):
        clipboard = QApplication.clipboard()
        if clipboard:
            self._add_keys(clipboard.text().splitlines())

    def _import_from_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            self.tr("导入 API Key"),
            "",
            self.tr("文本文件 (*.txt);;所有文件 (*)"),
        )
        if not file_path:
            return
        text = Path(file_path).read_text(encoding="utf-8").strip()
        self._add_keys(text.splitlines())

    def _clear_all_keys(self):
        self._save_keys([])
        self._reload_keys("")
        self._set_active_key("")

    def _delete_current_key(self):
        current_key = self.comboBox.currentText().strip()
        if not current_key:
            return
        keys = [key for key in self._stored_keys() if key != current_key]
        self._save_keys(keys)
        next_key = keys[0] if keys else ""
        self._reload_keys(next_key)
        self._set_active_key(next_key)
