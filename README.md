# AI Agent Browser Orchestrator

Hệ thống điều phối đa Agent giữa **Perplexity (Comet)** và **ChatGPT (GitHub Integration)** điều khiển tập trung qua giao diện Desktop **Python + NiceGUI**.

[![CI](https://github.com/thanhtupppp/dieuphoiagent/actions/workflows/ci.yml/badge.svg)](https://github.com/thanhtupppp/dieuphoiagent/actions/workflows/ci.yml)

---

## 🌟 Tính Năng Nổi Bật

- **Gắn kết CDP không phụ thuộc API trả phí:** Kết nối trực tiếp vào phiên trình duyệt Comet/Chrome (cổng 9222) qua Chrome DevTools Protocol, tận dụng phiên đăng nhập và các plugin có sẵn mà không lo Cloudflare/bot detection.
- **Phân vai rõ ràng:**
  - **Perplexity (Tab 1):** Tech Lead & Reviewer.
  - **ChatGPT (Tab 2):** Core Dev & Git Operator.
- **Giao thức thẻ [TAG] linh hoạt:** Bóc tách dữ liệu chuẩn xác bằng Regex có hỗ trợ markdown code block và heuristic fallback cho link PR / commit SHA.
- **Bộ nhận diện hoàn tất Streaming 3 lớp:** Kiểm tra nút Stop, tiến trình chạy Tool của ChatGPT và độ ổn định văn bản.
- **2 chế độ vận hành:** Chạy tự động (*Auto-pilot*) hoặc Duyệt từng bước (*Step-by-step*).
- **An toàn:** Ràng buộc tiền tố branch `ai-agent/`, trần vòng lặp `Max Loops` và nút ngắt khẩn cấp.

---

## 🚀 Cài Đặt

Project dùng **`pyproject.toml` + `uv.lock`** làm nguồn dependency chuẩn; không dùng `requirements.txt`.

### 1. Cài đặt môi trường

Cài [uv](https://docs.astral.sh/uv/) rồi chạy:

```bash
uv sync --locked
```

Nếu cần các optional extras:

```bash
uv sync --locked --all-extras
```

Cài Chromium cho Playwright khi chạy live:

```bash
uv run playwright install chromium
```

### 2. Khởi động trình duyệt Comet/Chrome với cổng CDP

```cmd
scripts\launch_comet.bat
```

Đăng nhập Perplexity và ChatGPT trên 2 tab nếu đây là lần đầu chạy profile.

### 3. Kiểm tra kết nối CDP

```bash
uv run python scripts/test_cdp.py
```

### 4. Khởi chạy giao diện NiceGUI

```bash
uv run python run.py
```

Mở `http://localhost:8080`.

---

## ✅ Quality Gates cục bộ

Chạy các lệnh giống CI trước khi mở PR:

```bash
uv sync --locked
uv run ruff format --check .
uv run ruff check .
uv run mypy core ui
uv run pytest --cov=core --cov-report=term-missing --cov-report=xml:coverage.xml --junitxml=test-results.xml
uv run pre-commit run --all-files
```

Secret scanning cục bộ có thể chạy bằng Gitleaks nếu đã cài binary:

```bash
gitleaks detect --source . --redact --no-banner
```

Các test đánh dấu `live` cần CDP/trình duyệt thật và được loại khỏi automated CI qua pytest config. CI không chứa API key, cookie, `.env` thật hoặc CDP credential.

Xem chính sách và troubleshooting chi tiết tại [`docs/ci.md`](docs/ci.md).

---

## 📂 Cấu Trúc Mã Nguồn

```text
dieuphoiagent/
├── config/
├── prompts/
├── core/
├── storage/
├── ui/
├── scripts/
├── tests/
├── docs/
├── pyproject.toml
├── uv.lock
└── run.py
```
