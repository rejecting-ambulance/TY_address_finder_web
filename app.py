# app.py
from flask import Flask, request, jsonify, render_template
import logging
from core import (
    setup_chrome_driver,
    search_address,
    simplify_address,
    fullwidth_to_halfwidth,
    format_simplified_address,
    remove_ling_with_condition,
    process_no_result_address,
    visual_len, # 雖然在 API 中不直接使用，但仍保留
    pad_text    # 雖然在 API 中不直接使用，但仍保留
)

app = Flask(__name__)

# 初始化日誌，確保在 Cloud Run 中能看到輸出
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 在應用程式啟動時預先初始化 WebDriver (單例模式)
# Cloud Run 會在容器首次啟動時執行此段，並在容器重用時跳過
# 這樣可以減少每個請求的啟動延遲。
try:
    _driver_instance, _wait_instance = setup_chrome_driver()
except Exception as e:
    logging.error(f"Failed to setup Chrome driver on app startup: {e}")
    # 在實際生產環境，可能需要更優雅地處理這個錯誤，例如健康檢查失敗

@app.route('/')
def index():
    """
    渲染一個簡單的 HTML 頁面，用於用戶輸入地址和顯示結果。
    """
    return render_template('index.html')

@app.route('/search_address_api', methods=['GET'])
def api_search_address():
    """
    API 端點，接收地址查詢並返回格式化後的結果。
    """
    global _driver_instance, _wait_instance

    address_query = request.args.get('address', '').strip()
    logging.info(f"Received API request for address: '{address_query}'")

    if not address_query:
        return jsonify({"error": "請提供 'address' 參數"}), 400

    # 確保 driver 和 wait 已經初始化
    if _driver_instance is None or _wait_instance is None:
        logging.error("WebDriver is not initialized. Attempting to re-initialize.")
        try:
            # 移除 'global' 關鍵字，因為這些變數已經在檔案頂層被定義為全局變數
            _driver_instance, _wait_instance = setup_chrome_driver()
        except Exception as e:
            return jsonify({"error": f"伺服器錯誤：WebDriver 初始化失敗 - {e}"}), 500


    try:
        data_address, shorter_address, last_address = simplify_address(address_query)
        result_address = search_address(_driver_instance, _wait_instance, shorter_address)

        full_address_result = ""
        simplified_result = ""
        formatted_simplified_result = ""

        if result_address == "找不到結果":
            full_address_result = "查無結果"
            simplified_result = process_no_result_address(data_address)
            formatted_simplified_result = format_simplified_address(simplified_result)
        else:
            full_address_result = f'桃園市{result_address}{last_address}'
            full_address_result = fullwidth_to_halfwidth(full_address_result)
            
            simplified_result = remove_ling_with_condition(full_address_result)
            formatted_simplified_result = format_simplified_address(simplified_result)
            
            # 根據原始邏輯，這裡簡化地址的格式化也使用了 full_address_result
            formatted_simplified_result_for_output = format_simplified_address(full_address_result)

        response_data = {

            "simplified_address": simplified_result,
            "formatted_simplified_address": formatted_simplified_result_for_output, # 使用這個變數來匹配您原始的輸出邏輯
            "status": "success" if full_address_result != "查無結果" else "no_result"
        }
        logging.info(f"Successfully processed address '{address_query}'. Result: {response_data}")
        return jsonify(response_data)

    except Exception as e:
        logging.error(f"Error processing address '{address_query}': {e}", exc_info=True)
        return jsonify({"error": f"處理地址時發生錯誤: {e}"}), 500

# Cloud Run 會使用 PORT 環境變數來決定服務監聽的端口
if __name__ == '__main__':
    # 在本地開發環境運行時使用，Cloud Run 會透過 Gunicorn 啟動
    app.run(host='0.0.0.0', port=8080)