# core.py
import re
import unicodedata
import logging
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options

import chromedriver_autoinstaller # <-- 暫時加回

# 設定日誌級別，Cloud Run 會自動收集 stdout/stderr
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logging.getLogger('selenium').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)

# 全局变量用于存储 WebDriver 实例和 WebDriverWait 实例
# 这样在同一个容器实例生命周期内可以重复使用，避免每次请求都重新初始化
_driver = None
_wait = None

def setup_chrome_driver():
    """
    初始化 Selenium WebDriver (Chrome)。
    配置為無頭模式，並針對伺服器環境進行最佳化。
    """
    # ✅ 自動安裝匹配的 ChromeDriver (僅供本地測試方便，部署時在 Dockerfile 處理)
    chromedriver_autoinstaller.install() # <-- 暫時加回
    global _driver, _wait
    if _driver is None:
        logging.info("Initializing Chrome WebDriver...")
        options = Options()
        options.add_argument('--headless=new')
        options.add_argument('--disable-gpu')
        options.add_argument('--no-sandbox') # Linux/Docker 環境下必需
        options.add_argument('--window-size=1920,1080')
        options.add_argument('--disable-dev-shm-usage') # 解決 Docker 內存共享問題
        options.add_argument('--disable-extensions')
        options.add_argument('--disable-web-security')
        options.add_argument('--disable-features=VizDisplayCompositor')
        options.add_argument('--disable-logging')
        options.add_argument('--log-level=3')
        options.add_argument('--silent')
        options.add_argument('--disable-crash-reporter')
        options.add_argument('--disable-in-process-stack-traces')
        options.add_argument('--disable-dev-tools')
        options.add_argument('--disable-background-timer-throttling')
        options.add_argument('--disable-renderer-backgrounding')
        options.add_argument('--disable-backgrounding-occluded-windows')
        options.add_argument('--disable-ipc-flooding-protection')
        options.add_experimental_option('excludeSwitches', ['enable-logging', 'enable-automation'])
        options.add_experimental_option('useAutomationExtension', False)
        
        try:
            _driver = webdriver.Chrome(options=options)
            _wait = WebDriverWait(_driver, 20) # 增加預設等待時間以應對網路延遲
            logging.info("Chrome WebDriver initialized successfully.")
        except Exception as e:
            logging.error(f"Failed to initialize Chrome WebDriver: {e}")
            raise RuntimeError(f"Failed to initialize Chrome WebDriver: {e}")
    return _driver, _wait

def wait_class_change(driver, element_id, origin_class, old_class, timeout=20):
    """
    等待指定元素的 class 屬性從 `origin_class` 改變，然後再從 `old_class` 改變。
    用於等待網頁元素狀態更新。
    """
    logging.debug(f"Waiting for class change on element ID: {element_id}")
    try:
        WebDriverWait(driver, timeout).until(
            lambda d: d.find_element(By.ID, element_id).get_attribute('class') != origin_class
        )
        WebDriverWait(driver, timeout).until(
            lambda d: d.find_element(By.ID, element_id).get_attribute('class') != old_class
        )
        logging.debug(f"Class changed for element ID: {element_id}")
    except Exception as e:
        logging.warning(f"Timeout waiting for class change on {element_id}: {e}")
        raise TimeoutError(f"Timeout waiting for class change on {element_id}")


def search_address(driver, wait, address):
    """
    使用 Selenium 訪問地址查詢網站，輸入地址並獲取結果。
    """
    logging.info(f"Searching address: {address}")
    try:
        driver.get('https://addressrs.moi.gov.tw/address/index.cfm?city_id=68000')
        address_box = wait.until(EC.presence_of_element_located((By.ID, 'FreeText_ADDR')))
        submit_button = driver.find_element(By.ID, 'ext-comp-1010')

        address_box.clear()
        address_box.send_keys(address)
        submit_button.click()
        
        # 等待網頁元素更新
        wait_class_change(driver, 'ext-gen97', 'x-panel-bwrap', 'x-panel-bwrap x-masked-relative x-masked')
        
        try:
            result = driver.find_element(By.XPATH, '//*[@id="ext-gen107"]/div/table/tbody/tr/td[2]/div')
            logging.info(f"Search result found: {result.text.strip()}")
            return result.text.strip()
        except Exception as e:
            logging.warning(f"Result element not found for address '{address}': {e}")
            return "找不到結果"
    except Exception as e:
        logging.error(f"Error during search_address for '{address}': {e}")
        raise RuntimeError(f"Error searching address: {e}")


def simplify_address(address):
    """
    將地址簡化：去除里、鄰、號後的文字，並將 '-' 替換為 '之'。
    回傳：(原地址, 簡化地址, 後綴)
    """
    original_address = address

    address = re.sub(r'([\u4e00-\u9fff]{1,5}區)[\u4e00-\u9fff]{1,2}里', r'\1', address)
    address = re.sub(r'(\d{1,3})鄰', '', address)
    address = address.replace('-', '之')

    split_chars = ['號', '及', '、', '.']
    split_indices = [(address.find(c), c) for c in split_chars if address.find(c) != -1]

    if split_indices:
        split_indices.sort()
        index, char = split_indices[0]
        if char == '號':
            simplified = address[:index + 1]
            suffix = address[index + 1:]
        else:
            simplified = address[:index]
            suffix = address[index:]
    else:
        simplified = address
        suffix = ''
    
    return original_address.strip(), simplified.strip(), suffix.strip()


def fullwidth_to_halfwidth(text):
    """
    將全形字元轉換為半形字元。
    """
    half_text = ''
    for char in text:
        code = ord(char)
        if code == 0x3000: # 全形空格
            code = 0x0020 # 半形空格
        elif 0xFF01 <= code <= 0xFF5E: # 全形字元範圍
            code -= 0xFEE0 # 轉換為半形
        half_text += chr(code)
    return half_text


def format_simplified_address(addr):
    """
    格式化簡化後的地址：
    1. 數字轉半形
    2. 去除空格
    3. 將「-」轉回「之」
    4. 去除「0」開頭的鄰編號，如 003鄰 ➜ 3鄰
    5. 阿拉伯數字轉中文段號（1~9段）
    """
    addr = fullwidth_to_halfwidth(addr)
    addr = addr.replace(' ', '')
    addr = addr.replace('-', '之')

    addr = re.sub(r'(\D)0*(\d+)鄰', r'\1\2鄰', addr)

    num_to_chinese = {'1': '一', '2': '二', '3': '三', '4': '四', '5': '五',
                      '6': '六', '7': '七', '8': '八', '9': '九'}

    def replace_road_section(match):
        num = match.group(1)
        return num_to_chinese.get(num, num) + '段'

    addr = re.sub(r'(\d)段', replace_road_section, addr)
    return addr.strip()


def remove_ling_with_condition(full_address):
    """
    刪除「里」與「鄰」間文字（含鄰），除非有特殊條件。
    """
    # 這裡的邏輯移除了原本被註釋掉的 exception_rules.json 相關部分
    return re.sub(r'(里).*?鄰', r'\1', full_address)


def process_no_result_address(original_address):
    """
    處理查無結果的地址：如果原地址有「里」，則將原地址作為結果返回，否則返回「查詢失敗」。
    """
    if "里" in original_address:
        return original_address
    else:
        return "查詢失敗"

# 這些視覺化輔助函數在後端服務中通常不需要，但如果需要進行文字處理可以保留
def visual_len(text):
    """ 計算文字的實際顯示寬度 """
    width = 0
    for ch in text:
        if unicodedata.east_asian_width(ch) in ('F', 'W'):
            width += 2  # 全形、寬字元
        else:
            width += 1  # 半形
    return width

def pad_text(text, target_width):
    """ 補足空格讓文字達到指定寬度 """
    pad_len = target_width - visual_len(text)
    return text + ' ' * max(pad_len, 0)