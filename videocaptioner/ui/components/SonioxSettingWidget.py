"""Soniox 转录设置组件"""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QVBoxLayout, QWidget
from qfluentwidgets import (
    ComboBoxSettingCard,
    SettingCardGroup,
    SingleDirectionScrollArea,
    SwitchSettingCard,
)
from qfluentwidgets import FluentIcon as FIF

from videocaptioner.core.asr.soniox_asr import SONIOX_MODELS
from videocaptioner.core.entities import TranscribeLanguageEnum

from ..common.config import cfg
from .ApiKeyComboSettingCard import ApiKeyComboSettingCard
from .EditComboBoxSettingCard import EditComboBoxSettingCard


class SonioxSettingWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()

    def setup_ui(self):
        self.main_layout = QVBoxLayout(self)

        self.scrollArea = SingleDirectionScrollArea(orient=Qt.Vertical, parent=self)
        self.scrollArea.setStyleSheet("QScrollArea{background: transparent; border: none}")

        self.container = QWidget(self)
        self.container.setStyleSheet("QWidget{background: transparent}")
        self.containerLayout = QVBoxLayout(self.container)

        self.setting_group = SettingCardGroup(self.tr("Soniox 设置"), self)

        self.api_key_card = ApiKeyComboSettingCard(
            cfg.soniox_api_key,
            cfg.soniox_api_keys,
            FIF.FINGERPRINT,
            self.tr("API Key"),
            self.tr("输入、粘贴或手动切换 Soniox API Key（也支持 SONIOX_API_KEY 环境变量）"),
            self.setting_group,
        )

        model_labels = [f"{k} - {v}" for k, v in SONIOX_MODELS.items()]
        self.model_card = EditComboBoxSettingCard(
            cfg.soniox_model,
            FIF.ROBOT,
            self.tr("Soniox 模型"),
            self.tr("选择 Soniox 转录模型，或直接输入 Soniox 最新/自定义模型名"),
            model_labels,
            self.setting_group,
        )

        self.language_card = ComboBoxSettingCard(
            cfg.transcribe_language,
            FIF.LANGUAGE,
            self.tr("源语言提示"),
            self.tr("作为 Soniox language_hints 传入，留空则自动识别多语言"),
            [lang.value for lang in TranscribeLanguageEnum],
            self.setting_group,
        )

        self.language_identification_card = SwitchSettingCard(
            FIF.LANGUAGE,
            self.tr("语言识别"),
            self.tr("为每个 token 返回识别语言，适合多语言混合音频"),
            cfg.soniox_language_identification,
            self.setting_group,
        )

        self.speaker_diarization_card = SwitchSettingCard(
            FIF.PEOPLE,
            self.tr("说话人分离"),
            self.tr("识别不同说话人并分别标记"),
            cfg.soniox_speaker_diarization,
            self.setting_group,
        )

        self.api_key_card.comboBox.setMinimumWidth(260)
        self.model_card.comboBox.setMinimumWidth(200)
        self.language_card.comboBox.setMinimumWidth(200)

        self.setting_group.addSettingCard(self.api_key_card)
        self.setting_group.addSettingCard(self.model_card)
        self.setting_group.addSettingCard(self.language_card)
        self.setting_group.addSettingCard(self.language_identification_card)
        self.setting_group.addSettingCard(self.speaker_diarization_card)

        self.containerLayout.addWidget(self.setting_group)
        self.containerLayout.addStretch(1)
        self.scrollArea.setWidget(self.container)
        self.scrollArea.setWidgetResizable(True)
        self.main_layout.addWidget(self.scrollArea)
