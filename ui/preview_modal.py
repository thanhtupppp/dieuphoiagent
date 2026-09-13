from typing import Optional, Callable

class PreviewModalState:
    def __init__(self):
        self.is_visible: bool = False
        self.target: str = ""
        self.payload: str = ""

    def open_modal(self, target: str, payload: str):
        self.is_visible = True
        self.target = target
        self.payload = payload

    def close_modal(self):
        self.is_visible = False

class PreviewModal:
    def __init__(self, on_approve: Callable[[str], None], on_reject: Callable[[], None]):
        self.on_approve = on_approve
        self.on_reject = on_reject
        self.state = PreviewModalState()
        self.dialog = None
        self.title_label = None
        self.payload_input = None
        self._build_dialog()

    def _build_dialog(self):
        try:
            from nicegui import ui
            with ui.dialog() as self.dialog, ui.card().classes("w-[700px] max-w-4xl p-6"):
                self.title_label = ui.label("Duyệt Payload chuyển giao").classes("text-xl font-bold")
                ui.label("Xem trước và chỉnh sửa nội dung trước khi gửi sang tab tiếp theo:").classes("text-sm text-gray-500 mb-2")
                
                self.payload_input = ui.textarea(label="Nội dung gửi").classes("w-full h-64 font-mono text-sm")
                
                with ui.row().classes("w-full justify-end mt-4 gap-3"):
                    ui.button("Hủy bỏ bước", color="red", on_click=self._handle_reject).props("flat")
                    ui.button("Duyệt & Gửi tiếp", color="green", on_click=self._handle_approve)
        except Exception:
            pass

    def show(self, target: str, payload: str):
        self.state.open_modal(target, payload)
        if self.title_label:
            self.title_label.text = f"Duyệt Payload chuyển giao sang {target}"
        if self.payload_input:
            self.payload_input.value = payload
        if self.dialog:
            self.dialog.open()

    def _handle_approve(self):
        self.state.close_modal()
        if self.dialog:
            self.dialog.close()
        text_val = self.payload_input.value if self.payload_input else self.state.payload
        self.on_approve(text_val)

    def _handle_reject(self):
        self.state.close_modal()
        if self.dialog:
            self.dialog.close()
        self.on_reject()
