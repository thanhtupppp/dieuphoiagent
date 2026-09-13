# AI Agent Browser Orchestrator

Hệ thống điều phối đa Agent giữa **Perplexity (Comet)** và **ChatGPT (GitHub Integration)** điều khiển tập trung qua giao diện Desktop **Python + NiceGUI**.

---

## 🌟 Tính Năng Nổi Bật

- **Gắn kết CDP không phụ thuộc API trả phí:** Kết nối trực tiếp vào phiên trình duyệt Comet/Chrome (cổng 9222) qua Chrome DevTools Protocol, tận dụng phiên đăng nhập và các plugin có sẵn mà không lo Cloudflare/bot detection.
- **Phân vai rõ ràng:** 
  - **Perplexity (Tab 1):** Tech Lead & Reviewer (nghiên cứu tài liệu mới, lập đặc tả kỹ thuật `[TASK_SPEC]`, nghiệm thu code).
  - **ChatGPT (Tab 2):** Core Dev & Git Operator (viết code, gọi GitHub Action/Plugin commit vào nhánh `ai-agent/`, mở PR).
- **Giao thức thẻ [TAG] linh hoạt:** Bóc tách dữ liệu chuẩn xác bằng Regex có hỗ trợ markdown code block và heuristic fallback cho link PR / commit SHA.
- **Bộ nhận diện hoàn tất Streaming 3 lớp:** Kiểm tra nút Stop, tiến trình chạy Tool của ChatGPT và độ ổn định văn bản trong 2.5s.
- **2 chế độ vận hành:** Chạy tự động (*Auto-pilot*) hoặc Duyệt từng bước (*Step-by-step*) với Dialog cho phép người dùng can thiệp sửa prompt trước khi chuyển tab.
- **An toàn tuyệt đối:** Ràng buộc tiền tố branch `ai-agent/`, trần vòng lặp `Max Loops` và nút ngắt khẩn cấp.

---

## 🚀 Hướng Dẫn Cài Đặt & Sử Dụng

### 1. Cài đặt môi trường
Khởi tạo môi trường ảo và cài đặt thư viện:
```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\playwright install chromium
```

### 2. Khởi động trình duyệt Comet/Chrome với cổng CDP
Chạy file script khởi động:
```cmd
scripts\launch_comet.bat
```
*(Đăng nhập Perplexity và ChatGPT trên 2 tab nếu đây là lần đầu chạy profile)*.

### 3. Kiểm tra kết nối trình duyệt
Chạy script kiểm tra nhanh cổng 9222:
```bash
.venv\Scripts\python scripts\test_cdp.py
```

### 4. Khởi chạy giao diện điều khiển NiceGUI
```bash
.venv\Scripts\python run.py
```
Mở trình duyệt truy cập: `http://localhost:8080`

---

## 📂 Cấu Trúc Mã Nguồn

```text
dieuphoiagent/
├── config/
│   ├── config.yaml          # Cấu hình cổng CDP (9222), timeout, max loops
│   └── selectors.json       # Tách riêng toàn bộ DOM selectors
├── prompts/
│   ├── perplexity_lead.md   # Prompt khởi tạo Tech Lead & chuẩn thẻ [TASK_SPEC]
│   └── chatgpt_dev.md       # Prompt khởi tạo Core Dev, ràng buộc nhánh ai-agent/
├── core/
│   ├── config_loader.py     # Loader cấu hình YAML và JSON
│   ├── cdp_connector.py     # Kết nối Playwright CDP, định danh tab & reconnect
│   ├── stream_detector.py   # Bộ nhận diện kết thúc sinh 3 lớp
│   ├── tag_protocol.py      # Schema Pydantic và Parser bóc tách thẻ [TAG]
│   └── orchestrator_fsm.py  # FSM điều phối vòng lặp, đếm loop, lưu session
├── storage/
│   └── sessions/            # Lưu trữ lịch sử từng task (JSON)
├── ui/
│   ├── app.py               # NiceGUI layout 2 cột
│   ├── log_streamer.py      # Async queue truyền log thời gian thực
│   └── preview_modal.py     # Modal xem trước & chỉnh sửa payload
├── scripts/
│   ├── launch_comet.bat     # Khởi động trình duyệt với port 9222
│   └── test_cdp.py          # Kiểm tra kết nối CDP
├── tests/                   # Toàn bộ test suite tự động (pytest)
├── requirements.txt
└── run.py                   # Điểm khởi chạy chính
```
