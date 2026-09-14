import asyncio
import logging
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.config_loader import load_config, load_selectors  # noqa: E402
from core.cdp_connector import CDPConnector  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("SmokeTestCDP")


async def run_smoke_test() -> bool:
    config = load_config(str(ROOT_DIR / "config" / "config.yaml"))
    selectors = load_selectors(str(ROOT_DIR / "config" / "selectors.json"))
    connector = CDPConnector(config, selectors)

    logger.info("=== BƯỚC 1: Kết nối CDP tới %s ===", config.cdp_url)
    connected = await connector.connect()
    assert connected, "Không thể kết nối tới CDP port 9222"
    assert connector.connected, "Thuộc tính connected phải là True"
    logger.info("-> Kết nối CDP thành công!")

    logger.info("=== BƯỚC 2: Nhận diện Tab lần 1 ===")
    p_tab_1, c_tab_1 = await connector.find_tabs()
    assert p_tab_1 is not None, "Không tìm thấy tab Perplexity"
    assert c_tab_1 is not None, "Không tìm thấy tab ChatGPT"
    logger.info("-> Perplexity Tab: %s", p_tab_1.url)
    logger.info("-> ChatGPT Tab: %s", c_tab_1.url)

    logger.info("=== BƯỚC 3: Nhận diện Tab lần 2 (Kiểm tra chống tạo tab trùng) ===")
    p_tab_2, c_tab_2 = await connector.find_tabs()
    assert p_tab_1 is p_tab_2, "Tab Perplexity bị tạo mới thay vì tái sử dụng!"
    assert c_tab_1 is c_tab_2, "Tab ChatGPT bị tạo mới thay vì tái sử dụng!"

    assert connector.browser is not None, "browser không được là None"
    context = connector.browser.contexts[0]
    pages = [p for p in context.pages if not p.is_closed()]
    perplexity_count = sum("perplexity.ai" in p.url for p in pages)
    chatgpt_count = sum("chatgpt.com" in p.url or "chat.openai.com" in p.url for p in pages)

    logger.info("-> Số lượng tab Perplexity active: %d", perplexity_count)
    logger.info("-> Số lượng tab ChatGPT active: %d", chatgpt_count)
    assert perplexity_count == 1, f"Có {perplexity_count} tab Perplexity (yêu cầu duy nhất 1)"
    assert chatgpt_count == 1, f"Có {chatgpt_count} tab ChatGPT (yêu cầu duy nhất 1)"

    logger.info("=== BƯỚC 4: Kiểm tra ngắt kết nối an toàn close() ===")
    await connector.close()
    assert connector.browser is None, "browser phải là None sau close()"
    assert connector.playwright is None, "playwright phải là None sau close()"
    assert connector.perplexity_tab is None, "perplexity_tab phải là None sau close()"
    assert connector.chatgpt_tab is None, "chatgpt_tab phải là None sau close()"
    assert not connector.is_connected, "is_connected phải là False sau close()"
    assert not connector.connected, "connected phải là False sau close()"
    logger.info("-> Toàn bộ tham chiếu đã được dọn sạch an toàn sau close()!")

    logger.info("=== BƯỚC 5: Kiểm tra kết nối lại sau close() ===")
    reconnected = await connector.reconnect()
    assert reconnected, "reconnect() phải thành công sau close()"
    assert connector.connected, "connector.connected phải là True sau reconnect()"
    assert connector.perplexity_tab is not None, "perplexity_tab phải tồn tại sau reconnect"
    assert connector.chatgpt_tab is not None, "chatgpt_tab phải tồn tại sau reconnect"
    logger.info("-> Reconnect thành công, tabs đã được khôi phục!")

    logger.info("=== BƯỚC 6: Teardown cuối cùng ===")
    await connector.close()
    logger.info("-> Đã ngắt kết nối Playwright client sạch sẽ!")

    logger.info("🎉 TẤT CẢ CÁC BƯỚC SMOKE TEST VỚI CHROME THẬT ĐÃ VƯỢT QUA!")
    return True


if __name__ == "__main__":
    success = asyncio.run(run_smoke_test())
    sys.exit(0 if success else 1)
