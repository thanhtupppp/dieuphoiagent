# Technical Design Document: AI Agent Browser Orchestrator

- **Tên dự án:** Multi-Agent Browser Orchestrator (Comet / Perplexity & ChatGPT / GitHub)
- **Tác giả:** Pair Programming (User & Antigravity)
- **Ngày tạo:** 2026-09-13
- **Trạng thái:** Approved by User (Design Specification)

---

## 1. Tổng Quan Dự Án (Executive Summary)

Dự án nhằm xây dựng một hệ thống Desktop Orchestrator tự động hóa chu trình khép kín giữa khâu **Nghiên cứu/Kiểm định (Perplexity AI trên trình duyệt Comet)** và khâu **Lập trình/Commit (ChatGPT kết hợp GitHub Plugin/Action)**.

Toàn bộ quá trình được điều phối thông qua một ứng dụng giao diện trực quan viết bằng **Python + Playwright + NiceGUI**, gắn kết với trình duyệt Comet/Chromium thông qua giao thức **Chrome DevTools Protocol (CDP)** trên cổng `9222`.

---

## 2. Phân Vai Hệ Thống (System Roles)

| Thực thể            | Vai trò đảm nhiệm           | Nền tảng / Công nghệ          | Nhiệm vụ chính                                                                                                                                                                                                                                                              |
| :------------------ | :-------------------------- | :---------------------------- | :-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Comet (Tab 1)**   | _Tech Lead & Code Reviewer_ | Perplexity AI (Web UI)        | • Tra cứu tài liệu, giải pháp mới nhất.<br>• Phân tích yêu cầu, xuất đặc tả kỹ thuật `[TASK_SPEC]`.<br>• Nghiệm thu PR sau commit: xuất `[NEEDS_REVISION]` nếu cần sửa hoặc `[STATUS: COMPLETED]` khi đạt chuẩn.                                                            |
| **ChatGPT (Tab 2)** | _Core Dev & Git Operator_   | ChatGPT + GitHub Tool/Plugin  | • Viết mã nguồn hoàn chỉnh.<br>• Gọi GitHub Plugin tạo nhánh có tiền tố `ai-agent/`, commit và mở/cập nhật PR.<br>• Xuất thẻ `[STATUS: COMMITTED]` kèm SHA/PR URL hoặc `[STATUS: ERROR]` khi gặp lỗi.                                                                       |
| **Orchestrator**    | _Project Manager & Router_  | Python + Playwright + NiceGUI | • Bắt nhịp streaming khi AI sinh xong câu trả lời và tool gọi xong.<br>• Parser Regex bóc tách các thẻ dữ liệu `[TAG]`.<br>• Điều phối FSM chuyển giao dữ liệu giữa 2 tab.<br>• Giao diện điều khiển (Auto-pilot & Step-by-step), đếm giới hạn vòng lặp, nút ngắt khẩn cấp. |

---

## 3. Kiến Trúc Module Đề Xuất (Modular Architecture)

Hệ thống được thiết kế theo mô hình **Modular Event-Driven FSM**, phân tách độc lập các lớp trách nhiệm để dễ dàng bảo trì và kiểm thử:

```text
dieuphoiagent/
├── config/
│   ├── config.yaml          # Cổng CDP (9222), browser path, timeout, default max_loops
│   └── selectors.json       # Tách riêng toàn bộ DOM selectors của Perplexity & ChatGPT
├── prompts/
│   ├── perplexity_lead.md   # Prompt khởi tạo vai trò Tech Lead & chuẩn thẻ [TASK_SPEC], [NEEDS_REVISION]
│   └── chatgpt_dev.md       # Prompt khởi tạo Core Dev, ràng buộc tiền tố branch 'ai-agent/' & thẻ [COMMITTED], [ERROR]
├── core/
│   ├── cdp_connector.py     # Kết nối CDP 9222, theo dõi & tự động reconnect khi mất kết nối
│   ├── stream_detector.py   # Nhận diện AI hoàn tất sinh câu trả lời & tool calling kết thúc
│   ├── tag_protocol.py      # Schema Pydantic và Regex parser trích xuất thẻ [TAG]
│   └── orchestrator_fsm.py  # FSM điều phối vòng lặp, đếm loop, xử lý rollback/abort
├── storage/
│   ├── logs/                # Lưu file log chạy hàng ngày (app.log, errors.log)
│   └── sessions/            # Lưu trữ session JSON/Markdown của từng task (toàn bộ payload, commit SHA, PR link)
├── ui/
│   ├── app.py               # NiceGUI layout 2 cột: Cột trái (Form/Điều khiển), Cột phải (Log Stream)
│   ├── log_streamer.py      # Async Queue truyền log thời gian thực lên giao diện
│   └── preview_modal.py     # Dialog xem trước, sửa payload (Step-by-step) & nút Abort/Rollback
├── scripts/
│   ├── launch_comet.bat     # Khởi động Comet/Chrome với cờ 9222 và profile riêng biệt
│   └── test_cdp.py          # Script kiểm tra kết nối CDP & in danh sách tab
├── document.md
├── requirements.txt
└── run.py                   # Điểm khởi chạy chính
```

---

## 4. Máy Trạng Thái Hữu Hạn (FSM Lifecycle)

```text
                    ┌─────────────────────────┐
                    │     [RECONNECTING]      │◄── (Mất kết nối CDP)
                    │ (Thử lại tối đa 3 lần)  │──► [CDP_ERROR] (Báo lỗi & dừng an toàn)
                    └───────────▲─────────────┘
                                │
[IDLE] ◄────────────────────────┼──────────────────────────────────┐
  │                             │                                  │
  │ (Người dùng bấm Start)      │                                  │ (Người dùng bấm Abort / Rollback)
  ▼                             │                                  ▼
[PERPLEXITY_SENDING] ──► [PERPLEXITY_WAITING]                [ABORTING]
  │                                                            │ - Thông báo hủy tác vụ
  ▼                                                            │ - Ghi nhận trạng thái vào storage/sessions/
[PERPLEXITY_PARSING]                                           │
  ├── [STATUS: COMPLETED] ────────────► [TASK_FINISHED]        ▼
  └── [STATUS: READY_FOR_DEV] hoặc [STATUS: NEEDS_REVISION]  [ABORTED] ──► [IDLE]
        │
        ▼
   (Kiểm tra chế độ)
   ├── [Step-by-step] ──► [WAITING_USER_APPROVAL] ──► (Duyệt) ─┐
   └── [Auto-pilot]   ─────────────────────────────────────────┘
        │
        ▼
[CHATGPT_SENDING] ──► [CHATGPT_WAITING] (Chờ sinh code & chạy GitHub Tool)
  │
  ▼
[CHATGPT_PARSING]
  ├── [STATUS: COMMITTED]
  │     ├── Loop >= Max Loops ──► [MAX_LOOPS_HALTED] (Dừng an toàn & cảnh báo)
  │     └── Còn lượt ───────────► Tăng Loop ──► Quay lại [PERPLEXITY_SENDING] để nghiệm thu
  │
  └── [STATUS: ERROR]
        └── Gửi [ERROR_DETAILS] về [PERPLEXITY_SENDING] để Perplexity phân tích sửa
```

---

## 5. Giao Thức Thẻ Dữ Liệu (Agent Tag Protocol)

### 5.1. Thẻ từ Perplexity (Tab 1)

#### A. Giao việc ban đầu (`[STATUS: READY_FOR_DEV]`)

```text
[SPEC_VERSION: 1.0]
[TASK]: <Mô tả chi tiết logic cần sửa hoặc tính năng cần viết>
[AFFECTED_FILES]: <Danh sách file liên quan>
[INSTRUCTIONS]: <Các yêu cầu bắt buộc về thư viện, phiên bản, thuật toán>
[STATUS: READY_FOR_DEV]
```

#### B. Yêu cầu sửa đổi khi review chưa đạt (`[STATUS: NEEDS_REVISION]`)

```text
[SPEC_VERSION: 1.0]
[BRANCH: ai-agent/<tên_branch_cũ>]
[PR_URL: <link_pull_request>]
[REVISION_NOTES]: <Phân tích chi tiết bug, thiếu sót hoặc lỗi cần refactor>
[INSTRUCTIONS]: <Các bước khắc phục cụ thể>
[STATUS: NEEDS_REVISION]
```

#### C. Nghiệm thu hoàn tất (`[STATUS: COMPLETED]`)

```text
[STATUS: COMPLETED]
[SUMMARY]: <Đánh giá tổng quan, xác nhận code đạt chuẩn và không còn lỗi tồn đọng>
```

### 5.2. Thẻ từ ChatGPT (Tab 2)

#### A. Commit và tạo/cập nhật PR thành công (`[STATUS: COMMITTED]`)

```text
[STATUS: COMMITTED]
[BRANCH: ai-agent/<tên_branch>]
[COMMIT_SHA: <mã_sha_7_ky_tu>]
[PR_URL: https://github.com/org/repo/pull/xxx]
[SUMMARY_CHANGES]: <Tóm tắt những thay đổi đã áp dụng vào codebase>
```

#### B. Báo cáo sự cố khi gặp lỗi (`[STATUS: ERROR]`)

```text
[STATUS: ERROR]
[BRANCH: ai-agent/<tên_branch>]
[ERROR_DETAILS]: <Chi tiết lỗi: conflict git, token GitHub hết hạn, fail tool, v.v.>
[ATTEMPT_COUNT]: <Số lần thử trong vòng lặp này>
```

### 5.3. Bộ Parser Regex & Fallback Heuristic

- **Biểu thức chính quy:** Bóc tách linh hoạt kể cả khi thẻ bị bọc trong Markdown code block hoặc có khoảng trắng thừa.
- **Heuristic Fallback:** Nếu ChatGPT quên sinh thẻ `[STATUS: COMMITTED]` nhưng câu trả lời có link GitHub PR (`github.com/.../pull/...`) và chuỗi SHA, parser tự động trích xuất và coi trạng thái là `COMMITTED`.

---

## 6. Cơ Chế CDP & Nhận Diện Kết Thúc Streaming

1. **Quản lý kết nối CDP (`cdp_connector.py`):**
   - Kết nối tới `http://localhost:9222` thông qua `playwright.chromium.connect_over_cdp`.
   - Tự động quét và gán `tab_perplexity` (URL chứa `perplexity.ai`) và `tab_chatgpt` (URL chứa `chatgpt.com` hoặc `chat.openai.com`, hoặc `chat.com`).
   - Hỗ trợ tự động kết nối lại khi trình duyệt reload hoặc ngắt đột ngột (thử tối đa 3 lần).
2. **Bộ nhận diện 3 lớp kết thúc sinh câu trả lời (`stream_detector.py`):**
   - **Lớp 1 (UI Button State):** Nút `Stop generating` biến mất hoàn toàn và nút `Send` quay lại trạng thái `enabled`.
   - **Lớp 2 (Tool Calling Guard):** Đợi các khối widget gọi tool GitHub trên giao diện ChatGPT hoàn tất (spinner loading biến mất).
   - **Lớp 3 (Text Stability / Idle Check):** Độ dài văn bản của khối tin nhắn cuối cùng ổn định, không thay đổi trong **2.5 giây liên tiếp**.
   - **Timeout Guard:** Cấu hình giới hạn thời gian tối đa (mặc định 240 giây) để cảnh báo kịp thời nếu tab bị kẹt.

---

## 7. Giao Diện Người Dùng & Các Cơ Chế An Toàn (NiceGUI)

1. **Layout 2 cột trực quan:**
   - **Cột trái:** Form cấu hình (Repo, Base Branch, Task Description, Max Loops Slider, Radio chọn Profile, Switch chọn Auto-pilot / Step-by-step) + Các nút điều khiển (`Start`, `Pause`, `Emergency Stop`, `Abort & Rollback`).
   - **Cột phải:** Thanh trạng thái (Loop Counter, FSM State) + Hệ thống Tabs phân loại Log (`All Logs`, `Perplexity Tab`, `ChatGPT Tab`) + Các nút tiện ích (`Copy Payload`, `Export Session`).
2. **Dialog Duyệt từng bước (`preview_modal.py`):**
   - Khi ở chế độ Step-by-step, dialog hiện lên trước khi forward nội dung sang tab kế tiếp, cho phép người dùng xem trước và trực tiếp sửa prompt/payload.
3. **Các lớp bảo vệ an toàn cốt lõi:**
   - **Branch Isolation:** Ép tiền tố `ai-agent/` trên mọi branch ChatGPT tạo ra.
   - **Max Loop Limiter:** Tự động dừng an toàn khi đạt trần số vòng lặp chỉ định (mặc định 5).
   - **Emergency Stop:** Dừng luồng xử lý ngay lập tức trong < 100ms.
   - **Session Persistence:** Tự động lưu toàn bộ dữ liệu phiên làm việc ra file JSON/Markdown trong `storage/sessions/`.

---

## 8. Kế Hoạch Triển Khai (Phase Breakdown)

1. **Giai đoạn 1: Lõi kết nối & Quản lý Browser:**
   - Tạo script `launch_comet.bat` và `config.yaml`.
   - Viết `core/cdp_connector.py` và script kiểm tra `scripts/test_cdp.py`.
2. **Giai đoạn 2: Giao thức Thẻ, Parser & Detector:**
   - Viết `core/tag_protocol.py` (Pydantic models, Regex parser, Fallbacks) kèm unit test.
   - Viết `core/stream_detector.py` (3-layer verification).
3. **Giai đoạn 3: Máy trạng thái FSM & Giao diện NiceGUI:**
   - Viết `core/orchestrator_fsm.py`.
   - Xây dựng giao diện NiceGUI hoàn chỉnh (`ui/app.py`, `ui/log_streamer.py`, `ui/preview_modal.py`).
4. **Giai đoạn 4: System Prompts & Kiểm thử thực tế (E2E Test):**
   - Hoàn thiện 2 file template markdown trong `prompts/`.
   - Chạy thử nghiệm luồng khép kín với một repo GitHub thử nghiệm.
