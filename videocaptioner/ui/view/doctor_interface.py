# -*- coding: utf-8 -*-

"""系统诊断界面"""

from typing import Optional

from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    CardWidget,
    InfoBar,
    PrimaryPushButton,
    ScrollArea,
    TitleLabel,
)
from qfluentwidgets import FluentIcon as FIF

from videocaptioner.cli.commands.doctor import Check, run_diagnostics
from videocaptioner.core.constant import (
    INFOBAR_DURATION_ERROR,
    INFOBAR_DURATION_SUCCESS,
)
from videocaptioner.ui.common.config import cfg
from videocaptioner.ui.common.dubbing_options import get_provider_option


class DoctorThread(QThread):
    """诊断线程"""

    finished = pyqtSignal(list)  # list[Check]
    error = pyqtSignal(str)

    def run(self):
        try:
            config = _build_doctor_config()
            checks = run_diagnostics(config, check_api=True)
            self.finished.emit(checks)
        except Exception as exc:
            self.error.emit(str(exc))


class TaskChip(QFrame):
    """任务标签组件"""

    def __init__(self, category: str, title: str, parent=None):
        super().__init__(parent)
        self.setObjectName("taskChip")
        self.setFixedHeight(62)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 8, 14, 8)
        layout.setSpacing(3)

        cat_label = QLabel(category, self)
        cat_label.setStyleSheet("font-size: 11px; color: #999999;")
        title_label = QLabel(title, self)
        title_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #CCCCCC;")
        title_label.setTextInteractionFlags(Qt.TextSelectableByMouse)

        layout.addWidget(cat_label)
        layout.addWidget(title_label)


class _CheckRow(QFrame):
    """单条诊断结果行"""

    def __init__(self, check: Check, parent=None):
        super().__init__(parent)
        self.setObjectName("checkRow")
        self.setStyleSheet("background: transparent;")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(12)

        # 状态图标
        status_icon = QLabel(self)
        if check.status == "ok":
            status_icon.setText("✓")
            status_icon.setStyleSheet("color: #38A169; font-size: 16px; font-weight: bold;")
        elif check.status == "warn":
            status_icon.setText("!")
            status_icon.setStyleSheet("color: #EAA300; font-size: 16px; font-weight: bold;")
        else:
            status_icon.setText("✗")
            status_icon.setStyleSheet("color: #E53E3E; font-size: 16px; font-weight: bold;")
        status_icon.setFixedWidth(24)
        layout.addWidget(status_icon)

        # 名称和消息
        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)

        name_label = QLabel(check.name, self)
        name_label.setStyleSheet("font-size: 13px; font-weight: bold; color: #CCCCCC;")
        text_layout.addWidget(name_label)

        msg_label = QLabel(check.message, self)
        msg_label.setStyleSheet("font-size: 12px; color: #999999;")
        msg_label.setWordWrap(True)
        text_layout.addWidget(msg_label)

        if check.fix:
            fix_label = QLabel(self.tr("建议: ") + check.fix, self)
            fix_label.setStyleSheet("font-size: 11px; color: #EAA300; font-style: italic;")
            fix_label.setWordWrap(True)
            text_layout.addWidget(fix_label)

        layout.addLayout(text_layout, 1)


class DoctorInterface(ScrollArea):
    """系统诊断界面"""

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setWindowTitle(self.tr("诊断"))
        self._doctor_thread: Optional[DoctorThread] = None
        self.scrollWidget = QWidget()
        self.pageLayout = QVBoxLayout(self.scrollWidget)
        self.taskGrid = QGridLayout()
        self.taskStrip = QFrame(self.scrollWidget)

        self._init_ui()

    def _init_ui(self):
        self.resize(1000, 800)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setViewportMargins(0, 80, 0, 20)
        self.setWidget(self.scrollWidget)
        self.setWidgetResizable(True)
        self.setObjectName("doctorInterface")
        self.scrollWidget.setObjectName("scrollWidget")

        self.setStyleSheet(
            """
            DoctorInterface, #scrollWidget {
                background-color: transparent;
            }
            QScrollArea {
                border: none;
                background-color: transparent;
            }
            QFrame#taskChip {
                background: rgba(255,255,255,0.05);
                border: 1px solid rgba(255,255,255,0.1);
                border-radius: 12px;
            }
        """
        )

        self.pageLayout.setSpacing(20)
        self.pageLayout.setContentsMargins(36, 30, 36, 30)

        # 标题栏
        header_layout = QHBoxLayout()
        self.title_label = TitleLabel(self.tr("诊断"), self.scrollWidget)
        header_layout.addWidget(self.title_label)
        header_layout.addStretch(1)
        self.run_button = PrimaryPushButton(
            self.tr("运行诊断"), self.scrollWidget, icon=FIF.SYNC
        )
        self.run_button.setFixedHeight(36)
        header_layout.addWidget(self.run_button)
        self.pageLayout.addLayout(header_layout)

        # 副标题
        self.subtitle_label = CaptionLabel(
            self.tr("检查当前任务会用到的服务和工具"), self.scrollWidget
        )
        self.pageLayout.addWidget(self.subtitle_label)

        # 任务标签条
        self.taskStrip.setObjectName("taskStrip")
        self.taskStrip.setStyleSheet(
            "QFrame#taskStrip { background: rgba(255,255,255,0.03);"
            "border: 1px solid rgba(255,255,255,0.08); border-radius: 16px; padding: 8px; }"
        )
        strip_layout = QVBoxLayout(self.taskStrip)
        strip_layout.setContentsMargins(12, 12, 12, 12)
        self.taskGrid.setHorizontalSpacing(10)
        self.taskGrid.setVerticalSpacing(10)
        strip_layout.addLayout(self.taskGrid)
        self.pageLayout.addWidget(self.taskStrip)

        # 诊断结果卡片
        self.result_card = CardWidget(self.scrollWidget)
        self.result_layout = QVBoxLayout(self.result_card)
        self.result_layout.setContentsMargins(20, 20, 20, 20)
        self.result_layout.setSpacing(8)

        # 初始状态提示
        self.placeholder_label = BodyLabel(
            self.tr("点击「运行诊断」开始检查系统环境"), self.result_card
        )
        self.placeholder_label.setAlignment(Qt.AlignCenter)
        self.placeholder_label.setStyleSheet(
            "color: #888888; font-size: 14px; padding: 60px 0; background: transparent;"
        )
        self.result_layout.addWidget(self.placeholder_label)

        self.pageLayout.addWidget(self.result_card)
        self.pageLayout.addStretch(1)

        # 连接信号
        self.run_button.clicked.connect(self._run)

    def showEvent(self, event):
        super().showEvent(event)
        # 每次显示时刷新任务标签（配置可能已改变）
        if not self._doctor_thread or not self._doctor_thread.isRunning():
            self._refresh_task_chips()

    def _refresh_task_chips(self):
        """刷新任务标签，显示当前配置"""
        _clear_layout(self.taskGrid)
        chips = _build_task_chips()
        columns = max(1, min(4, len(chips)))
        for index, chip_data in enumerate(chips):
            widget = TaskChip(chip_data[0], chip_data[1], self.taskStrip)
            widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            self.taskGrid.addWidget(widget, index // columns, index % columns)

    def _run(self):
        if self._doctor_thread and self._doctor_thread.isRunning():
            return

        self.run_button.setEnabled(False)
        self.run_button.setText(self.tr("诊断中..."))
        self._clear_results()

        # 显示"检查中"提示
        label = BodyLabel(self.tr("正在检查，请稍候..."), self.result_card)
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet(
            "color: #888888; font-size: 14px; padding: 60px 0; background: transparent;"
        )
        self.placeholder_label.hide()
        self.checking_label = label
        self.result_layout.addWidget(label)

        self._doctor_thread = DoctorThread()
        self._doctor_thread.finished.connect(self._on_finished)
        self._doctor_thread.error.connect(self._on_error)
        self._doctor_thread.start()

    def _clear_results(self):
        """清除诊断结果"""
        if hasattr(self, "checking_label"):
            self.checking_label.hide()
            self.checking_label.setParent(None)
        # 移除所有已添加的结果行
        for i in reversed(range(self.result_layout.count())):
            widget = self.result_layout.itemAt(i).widget()
            if widget and widget != self.placeholder_label:
                if not hasattr(self, "checking_label") or widget != self.checking_label:
                    widget.hide()
                    widget.setParent(None)

    def _on_finished(self, checks: list[Check]):
        self.run_button.setEnabled(True)
        self.run_button.setText(self.tr("重新诊断"))
        self._clear_results()

        if hasattr(self, "checking_label"):
            self.checking_label.hide()

        errors = sum(1 for c in checks if c.status == "error")
        warnings = sum(1 for c in checks if c.status == "warn")

        # 汇总信息
        summary_text = self.tr("诊断完成")
        if errors:
            summary_text += self.tr(" — {count} 项未通过").format(count=errors)
        elif warnings:
            summary_text += self.tr(" — {count} 项警告").format(count=warnings)
        else:
            summary_text += self.tr(" — 全部通过")

        summary = BodyLabel(summary_text, self.result_card)
        summary.setStyleSheet(
            "font-size: 15px; font-weight: bold; padding: 8px 0; background: transparent;"
            f"color: {'#E53E3E' if errors else '#EAA300' if warnings else '#38A169'};"
        )
        self.result_layout.addWidget(summary)

        # 每项检查结果
        for check in checks:
            row = _CheckRow(check, self.result_card)
            self.result_layout.addWidget(row)

        if errors:
            InfoBar.error(
                self.tr("诊断完成"),
                self.tr("发现 {count} 项需要处理").format(count=errors),
                duration=INFOBAR_DURATION_ERROR,
                parent=self,
            )
        else:
            InfoBar.success(
                self.tr("诊断完成"),
                self.tr("当前检查项全部通过")
                if not warnings
                else self.tr("诊断完成，有 {count} 项警告").format(count=warnings),
                duration=INFOBAR_DURATION_SUCCESS,
                parent=self,
            )

    def _on_error(self, message: str):
        self.run_button.setEnabled(True)
        self.run_button.setText(self.tr("重新诊断"))
        self._clear_results()
        if hasattr(self, "checking_label"):
            self.checking_label.hide()

        label = BodyLabel(self.tr("诊断出错: ") + message, self.result_card)
        label.setStyleSheet("color: #E53E3E; padding: 20px 0; background: transparent;")
        label.setAlignment(Qt.AlignCenter)
        self.result_layout.addWidget(label)

        InfoBar.error(
            self.tr("诊断失败"),
            message,
            duration=INFOBAR_DURATION_ERROR,
            parent=self,
        )


def _clear_layout(layout):
    """清空布局中的所有组件"""
    while layout.count():
        item = layout.takeAt(0)
        w = item.widget()
        if w:
            w.hide()
            w.setParent(None)
            w.deleteLater()


def _build_task_chips() -> list[tuple[str, str]]:
    """构建任务标签列表，显示当前配置"""
    chips: list[tuple[str, str]] = []

    # FFmpeg
    import shutil
    ffmpeg_path = shutil.which("ffmpeg")
    ffmpeg_status = "就绪" if ffmpeg_path else "未安装"
    chips.append(("FFmpeg / FFprobe", ffmpeg_status))

    # 转录服务
    transcribe_name = cfg.transcribe_model.value.value
    chips.append(("转录服务", transcribe_name))

    # 视频下载
    yt_dlp_path = shutil.which("yt-dlp")
    yt_dlp_status = "yt-dlp 就绪" if yt_dlp_path else "未安装"
    chips.append(("视频下载", yt_dlp_status))

    # 配音服务
    try:
        provider = get_provider_option(cfg.dubbing_provider.value)
        dub_name = provider.title
    except Exception:
        dub_name = cfg.dubbing_provider.value
    chips.append(("配音服务", dub_name))

    return chips


def _build_doctor_config() -> dict:
    """从当前 UI 配置构建诊断配置"""
    provider = cfg.dubbing_provider.value
    asr_name = cfg.transcribe_model.value.name.lower().replace("_", "-")

    return {
        "llm": {
            "api_key": _current_llm_api_key(),
            "api_base": _current_llm_api_base(),
            "model": _current_llm_model(),
        },
        "whisper_api": {
            "api_key": str(cfg.whisper_api_key.value or "").strip(),
            "api_base": str(cfg.whisper_api_base.value or "").strip(),
            "model": str(cfg.whisper_api_model.value or "whisper-1").strip(),
        },
        "fun_asr": {
            "api_key": str(cfg.fun_asr_api_key.value or "").strip(),
            "api_base": str(cfg.fun_asr_api_base.value or "").strip(),
            "model": str(cfg.fun_asr_model.value or "fun-asr").strip(),
        },
        "deepgram": {
            "api_key": str(cfg.deepgram_api_key.value or "").strip(),
            "model": str(cfg.deepgram_model.value or "nova-3-general").strip(),
        },
        "transcribe": {
            "asr": asr_name,
        },
        "subtitle": {
            "optimize": cfg.need_optimize.value,
            "split": cfg.need_split.value,
            "translate": cfg.need_translate.value,
            "render_mode": cfg.subtitle_render_mode.value.value,
        },
        "translate": {
            "service": "llm"
            if cfg.translator_service.value.name == "OPENAI"
            else cfg.translator_service.value.name.lower(),
        },
        "dubbing": {
            "provider": provider,
            "preset": cfg.dubbing_preset.value,
            "api_key": str(cfg.dubbing_api_key.value or "").strip(),
            "api_base": str(cfg.dubbing_api_base.value or "").strip(),
            "model": str(cfg.dubbing_model.value or "").strip(),
            "voice": str(cfg.dubbing_voice.value or "").strip(),
            "timing": cfg.dubbing_timing.value,
            "audio_mode": cfg.dubbing_audio_mode.value,
        },
    }


def _current_llm_api_key() -> str:
    service = cfg.llm_service.value
    value = {
        "OPENAI": cfg.openai_api_key.value,
        "SILICON_CLOUD": cfg.silicon_cloud_api_key.value,
        "DEEPSEEK": cfg.deepseek_api_key.value,
        "OLLAMA": cfg.ollama_api_key.value,
        "LM_STUDIO": cfg.lm_studio_api_key.value,
        "GEMINI": cfg.gemini_api_key.value,
        "CHATGLM": cfg.chatglm_api_key.value,
    }.get(service.name, "")
    return str(value or "").strip()


def _current_llm_api_base() -> str:
    service = cfg.llm_service.value
    value = {
        "OPENAI": cfg.openai_api_base.value,
        "SILICON_CLOUD": cfg.silicon_cloud_api_base.value,
        "DEEPSEEK": cfg.deepseek_api_base.value,
        "OLLAMA": cfg.ollama_api_base.value,
        "LM_STUDIO": cfg.lm_studio_api_base.value,
        "GEMINI": cfg.gemini_api_base.value,
        "CHATGLM": cfg.chatglm_api_base.value,
    }.get(service.name, "")
    return str(value or "").strip()


def _current_llm_model() -> str:
    service = cfg.llm_service.value
    value = {
        "OPENAI": cfg.openai_model.value,
        "SILICON_CLOUD": cfg.silicon_cloud_model.value,
        "DEEPSEEK": cfg.deepseek_model.value,
        "OLLAMA": cfg.ollama_model.value,
        "LM_STUDIO": cfg.lm_studio_model.value,
        "GEMINI": cfg.gemini_model.value,
        "CHATGLM": cfg.chatglm_model.value,
    }.get(service.name, "")
    return str(value or "").strip()
