import random
import json
import time
import os
from selenium.webdriver.chrome.service import Service
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver import ChromeOptions
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import WebDriverException, TimeoutException
# ----------------------------→爬取景点省份url-----------------------------------------
class GetSightUrl:
    def __init__(self):
        self.jd_login_url = "https://www.ctrip.com/"
        self.driver = self.Driver()
        self.citys_url_click = self.GetCityUrls(self.driver)


    def Driver(self):
        opt = ChromeOptions()
        opt.add_experimental_option('excludeSwitches', ['enable-automation'])
        opt.add_argument('--ignore-certificate-errors')
        opt.add_argument('--ignore-ssl-errors')
        opt.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36')
        driver_path = r"C:\Program Files\Google\Chrome\Application\chromedriver-win64\chromedriver.exe"
        service = Service(driver_path)
        driver = webdriver.Chrome(service=service, options=opt)
        driver.maximize_window()
        script = 'Object.defineProperty(navigator,"webdriver", {get: () => false,});'
        driver.execute_script(script)
        return driver

    # 获取各城市旅游页面url
    def GetCityUrls(self, driver):
        sight_citys = []
        find_city_elements = driver.find_elements(By.XPATH,
                                                  "/html/body/div[2]/div[2]/div/div/div/div/div[7]/div[1]/div[1]/div[2]/ul[1]/li/a")
        for e1 in find_city_elements:
            city = e1.text
            href = e1.get_attribute('href')

        if '/place/' in href:
            city_href = href.replace("/place/", "/sight/")
            sight_citys.append({'city_name': city, 'city_url': city_href})

        with open('D:/桌面/旅游知识图谱/sight_citys.txt', 'w', encoding='utf8') as f:
            f.write(json.dumps(sight_citys, ensure_ascii=False))

if __name__ == "__main__":
    su = GetSightUrl()
# ————————————————————————————城市名称（爬取景点数据时获取）→特色美食url-----------------------------------------
class GetFoodCityOptimized:
    def __init__(self):
        self.base_url = "https://www.ctrip.com/"
        self.driver = None
        self.processed_cities = []
        self.current_index = 0
        self.max_retries = 3
        self.batch_size = 20  # 每处理20个城市重启浏览器
        self._init_driver()
        self._load_processed_data()  # 加载已处理数据

    def _init_driver(self):
        """初始化浏览器实例"""
        opt = ChromeOptions()
        opt.add_experimental_option('excludeSwitches', ['enable-automation'])
        opt.add_experimental_option('detach', True)
        opt.add_argument('--ignore-certificate-errors')
        opt.add_argument('--ignore-ssl-errors')
        opt.add_argument(f'user-agent={self._random_user_agent()}')

        service = Service(r"C:\Program Files\Google\Chrome\Application\chromedriver-win64\chromedriver.exe")
        self.driver = webdriver.Chrome(service=service, options=opt)
        self.driver.maximize_window()
        self.driver.execute_script(
            'Object.defineProperty(navigator,"webdriver", {get: () => false,});'
        )

    def _random_user_agent(self):
        """生成随机User-Agent"""
        agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0"
        ]
        return random.choice(agents)

    def _load_cities(self):
        """正确读取城市文件"""
        file_path = "D:/旅游知识图谱/All_name_citys.txt"
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                # 处理可能的BOM头和尾部逗号
                content = content.replace('\ufeff', '').rstrip(',')
                return [city.strip() for city in content.split(',') if city.strip()]
        except Exception as e:
            print(f"城市文件读取失败: {str(e)}")
            return []

    def _load_processed_data(self):
        """加载已处理进度"""
        try:
            if os.path.exists('progress.json'):
                with open('progress.json', 'r') as f:
                    data = json.load(f)
                    self.current_index = data.get('index', 0)
                    self.processed_cities = data.get('processed', [])
        except:
            self.current_index = 0
            self.processed_cities = []

    def _save_progress(self):
        """保存处理进度"""
        with open('progress.json', 'w') as f:
            json.dump({
                'index': self.current_index,
                'processed': self.processed_cities
            }, f)

    def _restart_browser(self):
        """安全重启浏览器"""
        try:
            if self.driver:
                self.driver.quit()
        except:
            pass
        self._init_driver()
        print("\n--- 浏览器实例已重启 ---\n")
        time.sleep(random.uniform(3, 5))

    def process_cities(self):
        cities = self._load_cities()
        if not cities:
            print("未找到有效城市数据")
            return

        original_window = self.driver.window_handles[0]

        for idx in range(self.current_index, len(cities)):
            city = cities[idx]
            if city in self.processed_cities:
                continue

            # 每处理20个城市重启浏览器
            if (idx - self.current_index) % self.batch_size == 0 and idx != self.current_index:
                self._restart_browser()
                original_window = self.driver.window_handles[0]

            retries = 0
            while retries < self.max_retries:
                try:
                    self.driver.switch_to.window(original_window)
                    self.driver.get(self.base_url)

                    # 执行搜索操作
                    search_box = WebDriverWait(self.driver, 10).until(
                        EC.presence_of_element_located((By.XPATH, '//*[@id="_allSearchKeyword"]')))
                    search_box.clear()
                    search_box.send_keys(f"{city}美食")

                    search_button = WebDriverWait(self.driver, 10).until(
                        EC.element_to_be_clickable((By.ID, 'search_button_global')))
                    ActionChains(self.driver).move_to_element(search_button).click().perform()

                    # 处理新窗口
                    WebDriverWait(self.driver, 10).until(
                        lambda d: len(d.window_handles) > 1)
                    new_window = [w for w in self.driver.window_handles if w != original_window][0]
                    self.driver.switch_to.window(new_window)

                    # 获取并处理URL
                    current_url = self.driver.current_url
                    if "/restaurant/" in current_url:
                        food_url = current_url.split('#')[0].replace("/restaurant/", "/fooditem/")

                    self.processed_cities.append({
                        'city_name': city,
                        'food_url': food_url
                    })

                    # 关闭当前标签页
                    self.driver.close()
                    self.driver.switch_to.window(original_window)
                    break

                except (WebDriverException, TimeoutException) as e:
                    print(f"处理失败 [{city}], 重试 {retries + 1}/{self.max_retries}")
                    retries += 1
                    self._restart_browser()
                    original_window = self.driver.window_handles[0]
                finally:
                    self.current_index = idx + 1
                    self._save_progress()

            # 随机延迟防止频率过高
            time.sleep(random.uniform(1.5, 3.5))

        # 最终保存结果
        with open('D:/旅游知识图谱/Food_citys.txt', 'w', encoding='utf-8') as f:
            json.dump(self.processed_cities, f, ensure_ascii=False)
        # with open('D:/旅游知识图谱/restaurantlist_citys.txt', 'w', encoding='utf-8') as f:
        #     json.dump(self.restaurantlist_citys, f, ensure_ascii=False)
        self.driver.quit()


if __name__ == "__main__":
    crawler = GetFoodCityOptimized()
    crawler.process_cities()
#_______________________________________特色美食url→餐馆url——————————————————————————————————————————————————————
with open("D:/旅游知识图谱/Food_citys.txt", 'r', encoding='utf-8') as f:
    hotel_citys = []
    city_number = f.read()
    # 使用json解析文件内容
    i = json.loads(city_number)
    # 修改字段名
    for item in i:
        item['restaurant_url'] = item['food_url'].replace("/fooditem/", "/restaurantlist/")
        del item['food_url'] # 删除旧的'url'字段
        print(item)

# 保存结果
with open("D:/旅游知识图谱/Restaurant_citys.txt", 'w', encoding='utf8') as f:
    json.dump(i, f, ensure_ascii=False)
    print("数据已保存")