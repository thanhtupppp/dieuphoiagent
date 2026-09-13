# CI/CD Quality Gates

## Mục tiêu

GitHub Actions kiểm tra package và các quality gate độc lập để lỗi dễ chẩn đoán. Workflow chạy khi:

- push vào `master`;
- mở/cập nhật Pull Request;
- chạy thủ công bằng `workflow_dispatch`.

Repository hiện dùng `master` làm branch mặc định; workflow không tự tạo hoặc đổi tên branch mặc định.

## Các job

| Job | Kiểm tra |
| --- | --- |
| `package` | `uv sync --locked` và `uv build` |
| `format` | `uv run ruff format --check .` |
| `lint` | `uv run ruff check .` |
| `typecheck` | `uv run mypy core ui` |
| `test` | pytest + coverage + JUnit report + artifact |
| `pre-commit` | `uv run pre-commit run --all-files` |
| `secret-scan` | Gitleaks trên toàn bộ Git history |

Tất cả job dùng Python 3.12, phù hợp với metadata `requires-python = ">=3.12"` và cấu hình tool hiện tại. Dependency được cài bằng `uv sync --locked`; CI không regenerate lockfile.

## Dependency cache

`astral-sh/setup-uv` bật cache cho uv. Cache chỉ phục vụ tốc độ tải dependency; việc cài đặt vẫn dùng `uv.lock`, vì vậy cache không thay đổi resolution hoặc bỏ qua lock verification.

## Least privilege và fork PR

Workflow khai báo `permissions: contents: read`. Không dùng secret dự án để build/test. `GITHUB_TOKEN` chỉ được truyền cho Gitleaks action vì action có thể dùng GitHub API cho metadata; không cấp quyền ghi. Fork PR vẫn chạy các quality gate không cần secret riêng.

Secret scanning dùng Gitleaks thay vì GitHub Advanced Security để không phụ thuộc gói GitHub trả phí. Gitleaks được chạy với redaction/summary và không upload artifact của scanner. Không đặt credential thật trong fixture, test hoặc log.

> Nếu sau này bật GitHub-native secret scanning/Advanced Security, quyền và tính khả dụng phụ thuộc repository visibility, tổ chức và gói GitHub; cần review lại `permissions` trước khi bật SARIF upload.

## Test artifacts

Job `test` luôn cố gắng upload `test-results.xml`, `coverage.xml`, `.coverage` và `htmlcov/`, kể cả khi pytest thất bại. Artifact giữ trong 14 ngày. Không đưa `.env`, credential hoặc file storage session vào artifact.

## CDP / live integration

Các test cần browser/CDP thật phải được đánh dấu `@pytest.mark.live`. Cấu hình pytest mặc định chạy `-m 'not live'`, vì môi trường GitHub-hosted runner không đảm bảo profile trình duyệt, đăng nhập, CDP endpoint hoặc credential. Đây là chủ ý để CI kiểm tra logic ổn định mà không giả lập thành công một integration phụ thuộc môi trường ngoài.

## Chạy local trước khi mở PR

```bash
uv sync --locked
uv run ruff format --check .
uv run ruff check .
uv run mypy core ui
uv run pytest --cov=core --cov-report=term-missing --cov-report=xml:coverage.xml --junitxml=test-results.xml
uv run pre-commit run --all-files
```

Nếu cần kiểm tra secret local, cài Gitleaks và chạy:

```bash
gitleaks detect --source . --redact --no-banner
```

## Xử lý lỗi

1. **`uv sync --locked` fail:** kiểm tra `pyproject.toml` có thay đổi dependency nhưng `uv.lock` chưa được cập nhật. Chỉ regenerate lock khi dependency thực sự thay đổi.
2. **Ruff fail:** chạy `uv run ruff format .` hoặc sửa lint theo output, sau đó chạy lại quality gates.
3. **Mypy fail:** sửa annotation/type boundary; không hạ strictness chỉ để làm CI xanh.
4. **Pytest fail:** đọc `test-results.xml`/coverage artifact và sửa test hoặc code. Không bật `live` test trong CI.
5. **Pre-commit fail:** chạy hook tương ứng local rồi commit lại thay đổi cần thiết.
6. **Secret scan fail:** revoke/rotate credential nếu đó là secret thật; sau đó loại bỏ khỏi history theo quy trình bảo mật của repository. Không paste secret vào issue/PR.

## Thay đổi dependency

PR CI này không thêm dependency runtime và không yêu cầu cập nhật `uv.lock`. Các tool quality gate đã có trong dependency group `dev` của `pyproject.toml`.
