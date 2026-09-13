Dưới đây là bản **Tài liệu Phương án Phát triển (Technical Development Proposal)** chi tiết cho dự án xây dựng hệ thống điều phối đa Agent giữa **Comet (Perplexity)** và **ChatGPT (GitHub Integration)**, được quản lý tập trung bằng **Python + Playwright + NiceGUI**.

---

# TÀI LIỆU PHƯƠNG ÁN PHÁT TRIỂN HỆ THỐNG

## DỰ ÁN: AI AGENT BROWSER ORCHESTRATOR (COMET & CHATGPT)

---

### 1. TỔNG QUAN DỰ ÁN (EXECUTIVE SUMMARY)

- **Tên dự án:** Multi-Agent Browser Orchestrator (Comet - ChatGPT - GitHub).
- **Mục tiêu cốt lõi:** Tự động hóa chu trình khép kín giữa khâu **Nghiên cứu/Kiểm định (Perplexity)** và khâu **Lập trình/Commit (ChatGPT)** trên trình duyệt Comet mà không cần can thiệp thủ công, điều khiển qua một ứng dụng Desktop (Python + NiceGUI).
- **Đối tượng sử dụng:** Lập trình viên cá nhân hoặc Tech Lead muốn tăng tốc độ nghiên cứu, giải quyết bug và cập nhật codebase theo tài liệu kỹ thuật mới nhất.

---

### 2. PHÂN VAI HỆ THỐNG (SYSTEM ROLES)

| Thực thể          | Vai trò đảm nhiệm      | Công nghệ / Nền tảng | Nhiệm vụ chính                              |
| ----------------- | ---------------------- | -------------------- | ------------------------------------------- |
| **Comet (Tab 1)** | _Tech Lead & Reviewer_ | Perplexity AI (Web)  | • Tra cứu tài liệu, framework mới nhất.<br> |

<br>• Phân tích lỗi, lập đặc tả kỹ thuật (`[TASK_SPEC]`).<br>

<br>• Phản biện và nghiệm thu code sau commit. |
| **ChatGPT (Tab 2)** | _Core Dev & Git Operator_ | ChatGPT + GitHub App/Action | • Viết mã nguồn hoàn chỉnh.<br>

<br>• Gọi plugin GitHub tạo nhánh/commit/mở PR.<br>

<br>• Báo cáo trạng thái và mã SHA/URL. |
| **Orchestrator** | _Project Manager & Router_ | Python + Playwright + NiceGUI | • Bắt nhịp DOM khi AI sinh xong câu trả lời.<br>

<br>• Bóc tách và chuyển giao dữ liệu giữa 2 tab.<br>

<br>• Giao diện điều khiển, nút khẩn cấp và bảo vệ an toàn. |

---

### 3. KIẾN TRÚC HỆ THỐNG (SYSTEM ARCHITECTURE)

```text
┌─────────────────────────────────────────────────────────────┐
│               GIAO DIỆN ĐIỀU KHIỂN (NICEGUI)                 │
│  [Cấu hình Repo/Branch] [Mục tiêu Task] [Nút Start / Stop]  │
│  [Log tương tác Perplexity]    [Log trạng thái Git ChatGPT] │
└──────────────────────────────┬──────────────────────────────┘
                               │ (Async Event Queue)
┌──────────────────────────────▼──────────────────────────────┐
│           ENGINE ĐIỀU PHỐI (PYTHON PLAYWRIGHT)              │
│  - Parser bóc tách Tag ([TASK], [COMMIT], [DONE])          │
│  - Bộ đếm vòng lặp an toàn (Loop Limiter & Timeout Guard)   │
└──────────────────────────────┬──────────────────────────────┘
                               │ (Chrome DevTools Protocol - Port 9222)
┌──────────────────────────────▼──────────────────────────────┐
│                 TRÌNH DUYỆT COMET (CHROMIUM)                │
│   ┌──────────────────────────┐   ┌───────────────────────┐   │
│   │   TAB 1: PERPLEXITY      │   │    TAB 2: CHATGPT     │   │
│   │   - Tìm kiếm web         │   │   - Viết code         │   │
│   │   - Lập spec & kiểm định │   │   - GitHub Plugin     │   │
│   └─────────────▲────────────┘   └───────────┬───────────┘   │
└─────────────────┼────────────────────────────┼───────────────┘
                  │                            ▼
            (Tài liệu mới)             (GitHub Repository)

```

---

### 4. GIAO THỨC GIAO TIẾP DỮ LIỆU (AGENT PROTOCOL)

Để Orchestrator bóc tách dữ liệu chính xác bằng mã thuần (Regex) mà không bị nhiễu câu chữ chào hỏi, hai tab được ép chuẩn theo các cấu trúc thẻ định dạng:

#### A. Định dạng đầu ra của Perplexity (Tab 1)

```text
[SPEC_VERSION: 1.0]
[TASK]: <Mô tả chi tiết logic cần sửa hoặc tính năng cần viết>
[AFFECTED_FILES]: <Danh sách file liên quan>
[INSTRUCTIONS]: <Các yêu cầu bắt buộc về thư viện, phiên bản, thuật toán>
[STATUS: READY_FOR_DEV]

```

#### B. Định dạng đầu ra của ChatGPT (Tab 2)

```text
[STATUS: COMMITTED]
[BRANCH: feature/xxx]
[COMMIT_SHA: 9f8a2bc]
[PR_URL: https://github.com/org/repo/pull/12]
[SUMMARY_CHANGES]: <Tóm tắt những thay đổi vừa áp dụng>

```

#### C. Điều kiện kết thúc (Termination Condition)

Khi Perplexity đánh giá mã nguồn đã hoàn thành và đạt tiêu chuẩn, Perplexity sẽ xuất ra:

```text
[STATUS: COMPLETED]
[SUMMARY]: Đã hoàn thiện toàn bộ yêu cầu, không còn lỗi tồn đọng.

```

Orchestrator bắt được thẻ này sẽ tự động ngắt vòng lặp và thông báo thành công trên màn hình.

---

### 5. QUY TRÌNH HOẠT ĐỘNG (WORKFLOW STEP-BY-STEP)

```text
[Bắt đầu] ──► Người dùng nhập Repo, Branch, Mục tiêu trên UI NiceGUI ──► Bấm [Start]
     │
     ▼
[Bước 1] Orchestrator gửi mục tiêu vào Tab Perplexity qua CDP
     │
     ▼
[Bước 2] Perplexity tra cứu, trả về [TASK_SPEC]
     │
     ▼
[Bước 3] Orchestrator bắt sự kiện xong, copy [TASK_SPEC] paste sang Tab ChatGPT
     │
     ▼
[Bước 4] ChatGPT viết mã, kích hoạt plugin GitHub commit vào branch chỉ định
     │
     ▼
[Bước 5] Orchestrator lấy link PR & [SUMMARY_CHANGES] gửi ngược lại Perplexity
     │
     ▼
[Bước 6] Perplexity kiểm tra lại:
     ├── Nếu phát hiện bug / thiếu sót ──► Quay lại [Bước 2] (Vòng lặp tiếp theo)
     └── Nếu đạt tiêu chuẩn ──────────────► Xuất [STATUS: COMPLETED] ──► [Kết thúc]

```

---

### 6. LỘ TRÌNH TRIỂN KHAI (IMPLEMENTATION ROADMAP)

#### Giai đoạn 1: Xây dựng lõi kết nối (Core CDP & Selector Engine) - _Thời lượng: 3–4 ngày_

- Cấu hình shortcut khởi động Comet với cờ `--remote-debugging-port=9222`.
- Xây dựng module Playwright để tự nhận diện chính xác 2 tab (Comet/ChatGPT).
- Xử lý DOM Selector và sự kiện submit:
- ChatGPT: Target selector `#prompt-textarea`, mô phỏng typing và dispatch sự kiện React.
- Perplexity/Comet: Target ô textarea, chờ đợi nút dừng/quay loading biến mất.

- Thử nghiệm truyền một chuỗi text cố định qua lại giữa 2 tab thành công.

#### Giai đoạn 2: Phát triển giao diện Desktop (NiceGUI Control Panel) - _Thời lượng: 3 ngày_

- Xây dựng layout Native UI 2 cột:
- **Cột trái:** Form cấu hình (Repo, Branch, Task Description, Slider Max Loops, nút Start/Pause/Stop).
- **Cột phải:** Log viewer hiển thị nội dung theo thời gian thực (phân tách màu riêng cho 2 tab).

- Tích hợp cờ ngắt an toàn (`is_running = False` khi bấm nút Stop).
- Đưa vào cơ chế đếm số vòng lặp tối đa để chống kẹt vô tận.

#### Giai đoạn 3: Chuẩn hóa Prompt & Kiểm thử thực tế - _Thời lượng: 4–5 ngày_

- Thiết kế bộ **Initial System Prompt** cho 2 bên để đảm bảo luôn tuân thủ cấu trúc thẻ `[TAG]`.
- Chạy thử nghiệm thực tế với 1 bài toán nhỏ (ví dụ: tạo 1 utility function đơn giản trong repository).
- Đo lường thời gian trễ của plugin GitHub trên ChatGPT để tinh chỉnh `timeout` và cơ chế retry phù hợp.

#### Giai đoạn 4 (Tùy chọn mở rộng): Tích hợp LLM Trọng tài - _Thời lượng: 2–3 ngày_

- Bổ sung API LLM siêu nhẹ (như GPT-4o-mini hoặc Gemini Flash) vào Orchestrator.
- Dùng làm bộ lọc nén ngữ cảnh nếu đoạn hội thoại dài quá 5 vòng lặp, hoặc làm trọng tài phân xử nếu 2 bên tranh luận không hồi kết.

---

### 7. MA TRẬN RỦI RO VÀ GIẢI PHÁP (RISK MANAGEMENT)

| Rủi ro kỹ thuật                            | Mức độ     | Phương án dự phòng / Giải pháp                                                                                                 |
| ------------------------------------------ | ---------- | ------------------------------------------------------------------------------------------------------------------------------ |
| **Giao diện Web AI thay đổi DOM**          | Trung bình | Tách riêng file `selectors.json`. Khi giao diện web cập nhật class, chỉ cần sửa selector mà không cần sửa code logic.          |
| **ChatGPT commit nhầm vào nhánh main**     | Cao        | Prompt ràng buộc chặt chẽ + Ép ChatGPT luôn tạo branch có tiền tố `ai-agent/`. Người dùng chỉ merge qua Pull Request thủ công. |
| **AI nói chuyện vòng vo làm hết token**    | Trung bình | Đặt giới hạn cứng `Max Iterations = 5` trên UI. Nếu hết 5 vòng chưa xong, hệ thống tự dừng và yêu cầu người dùng duyệt tay.    |
| **Plugin GitHub bị timeout hoặc lỗi mạng** | Thấp       | Bổ sung hàm kiểm tra trạng thái lỗi từ DOM của ChatGPT; nếu nút reload xuất hiện thì gửi lệnh retry tự động.                   |

---

### 8. BƯỚC HÀNH ĐỘNG TIẾP THEO (NEXT STEPS)

1. Thiết lập sẵn phím tắt hoặc file script `.bat` / `.sh` để mở Comet với cổng 9222.
2. Kiểm tra thực tế selector ô chat và nút gửi hiện tại trên trình duyệt của bạn để chuẩn hóa code Playwright.
3. Chạy thử nghiệm script khung NiceGUI đã chuẩn bị để kiểm tra luồng truyền tin cơ bản.
