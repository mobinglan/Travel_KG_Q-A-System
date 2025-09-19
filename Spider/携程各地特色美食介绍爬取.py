from py2neo import Graph, Node, Relationship
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver import ChromeOptions
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import random
import time
import json
import logging
import re
import os

os.environ["NEO4J_POOL_SIZE"] = "20"

# 配置日志记录
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('delicacy_crawler.log'),
        logging.StreamHandler()
    ]
)

class Neo4jClient:
    def __init__(self, uri, user, password):
        self.graph = Graph(uri, auth=(user, password))
        self._setup_constraints()
        self.current_batch = []
        self.batch_size = 15

    def _setup_constraints(self):
        """设置数据库约束"""
        try:
            self.graph.run("CREATE CONSTRAINT IF NOT EXISTS FOR (c:City) REQUIRE c.name IS UNIQUE")
            self.graph.run("CREATE CONSTRAINT IF NOT EXISTS FOR (d:Delicacy) REQUIRE d.city_uid IS UNIQUE")
        except Exception as e:
            logging.warning(f"约束设置异常: {str(e)[:200]}")

    def get_city_node(self, city_name):
        """获取已存在的城市节点"""
        query = """
            MATCH (c:City {name: $city_name})
            RETURN c LIMIT 1
        """
        result = self.graph.run(query, city_name=city_name).data()
        return result[0]['c'] if result else None

    def create_delicacy(self, delicacy_data, detail_data, city_name):
        """创建美食节点（关联现有城市）"""
        try:
            city_node = self.get_city_node(city_name)
            if not city_node:
                logging.error(f"城市节点不存在: {city_name}")
                return None

            # 生成唯一标识
            uid = f"{city_name}_{delicacy_data.get('name', '')}"

            combined = self._clean_data({
                **delicacy_data,
                **detail_data,
                "city_uid": uid,  # 城市+美食名组合
                "city": city_name,
                "city_url": city_node["url"]
            })

            if self._delicacy_exists(uid):
                logging.info(f"跳过已存在美食: {uid}")
                return None

            self.current_batch.append((combined, city_node))

            if len(self.current_batch) >= self.batch_size:
                self._commit_batch()

            return combined
        except Exception as e:
            logging.error(f"准备美食数据失败: {e}")
            return None

    def _delicacy_exists(self, uid):
        """基于复合标识检查存在性"""
        query = "MATCH (d:Delicacy {city_uid: $uid}) RETURN d LIMIT 1"
        return bool(self.graph.run(query, uid=uid).data())

    def _commit_batch(self):
        """批量提交优化"""
        if not self.current_batch:
            return

        tx = self.graph.begin()
        try:
            for data, city_node in self.current_batch:
                delicacy = Node("Delicacy", **data)
                tx.create(delicacy)

                # 创建关系
                rel = Relationship(delicacy, "LOCATED_IN", city_node)
                tx.create(rel)

                # 特征关系
                if data.get("features"):
                    for feature in data["features"].split():
                        feature_node = Node("Feature", name=feature.strip())
                        tx.merge(feature_node, "Feature", "name")
                        tx.create(Relationship(delicacy, "HAS_FEATURE", feature_node))

            tx.commit()
            logging.info(f"成功提交 {len(self.current_batch)} 个美食")
            self.current_batch = []
        except Exception as e:
            tx.rollback()
            logging.error(f"批量提交失败: {e}")
            self.current_batch = []

    def _clean_data(self, raw_data):
        cleaned = {}
        for k, v in raw_data.items():
            if isinstance(v, str):
                v = re.sub(r'[\u200b\xa0]', '', v).strip()
                if k == "price" and "￥" in v:
                    v = v.replace("￥", "").strip()
            cleaned[k] = v
        return cleaned


class DelicacyCrawler:
    def __init__(self):
        self.driver = self._init_driver()
        self.neo4j = Neo4jClient("bolt://localhost:7687", "neo4j", "mo301329")
        self.processed = 0
        self.errors = 0
        self.valid_cities = self._load_valid_cities()

    def _init_driver(self):
        opt = ChromeOptions()
        opt.add_argument("--headless")
        opt.add_argument("--disable-gpu")
        opt.add_argument("--incognito")
        opt.add_experimental_option('excludeSwitches', ['enable-automation'])
        opt.add_argument('--ignore-certificate-errors')

        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0"
        ]
        opt.add_argument(f"user-agent={random.choice(user_agents)}")

        prefs = {"profile.managed_default_content_settings.images": 2}
        opt.add_experimental_option("prefs", prefs)

        service = Service(r"C:\Program Files\Google\Chrome\Application\chromedriver-win64\chromedriver.exe")
        return webdriver.Chrome(service=service, options=opt)
    def _load_valid_cities(self):
        """加载已存在的城市数据"""
        query = "MATCH (c:City) RETURN c.name as name, c.url as url"
        return {row['name']: row['url'] for row in self.neo4j.graph.run(query)}

    def process_cities(self):
        try:
            with open("D:/旅游知识图谱/完整的/Food_citys.txt", 'r', encoding='utf-8') as f:
                cities = json.load(f)

            valid_data = [c for c in cities if c['city_name'] in self.valid_cities]
            logging.info(f"有效城市数量: {len(valid_data)}/{len(cities)}")

            for idx, city in enumerate(valid_data):
                try:
                    if idx % 3 == 0:
                        self._restart_browser()

                    self._process_city(city['city_name'], city['food_url'])
                    self.processed += 1
                except Exception as e:
                    self.errors += 1
                    logging.error(f"处理失败 [{city.get('city_name')}]: {str(e)[:200]}")

            self.neo4j._commit_batch()
            logging.info(f"处理完成！成功：{self.processed} 失败：{self.errors}")
        except Exception as e:
            logging.error(f"文件处理失败: {str(e)}")

    def _process_city(self, city_name, city_url):
        """处理单个城市的美食数据"""
        logging.info(f"开始处理城市: {city_name}")
        try:
            self._load_city_page(city_url)

            # 检查是否有特色美食列表
            try:
                WebDriverWait(self.driver, 15).until(
                    EC.presence_of_element_located((By.CLASS_NAME, "rdetailbox")))

                # 处理分页
                page_count = 1
                while True:
                    logging.info(f"正在处理第 {page_count} 页")
                    self._process_delicacies(city_name)

                    # 尝试翻页
                    if not self._go_to_next_page():
                        break

                    page_count += 1
                    time.sleep(random.uniform(1, 3))  # 随机等待防止被封

            except TimeoutException:
                logging.info(f"城市 {city_name} 无特色美食列表，跳过")
                return
        except Exception as e:
            logging.error(f"城市处理失败: {str(e)[:200]}")
        finally:
            self.neo4j._commit_batch()

    def _process_delicacies(self, city_name):
        """处理当前页的所有特色美食"""
        elements = self.driver.find_elements(By.XPATH, '//div[@class="rdetailbox"]')

        if not elements:
            logging.info(f"当前页面没有找到美食项目")
            return

        logging.info(f"发现 {len(elements)} 个特色美食")

        for element in elements:
            try:
                # 提取基本信息
                name_element = element.find_element(By.XPATH, './/dl/dt/a')
                name = name_element.text.strip()
                url = name_element.get_attribute('href').strip()

                # 获取介绍信息
                introduce = self._get_delicacy_introduce(url) if url else "无详情链接"

                # 创建节点
                self.neo4j.create_delicacy(
                    {"name": name, "url": url},
                    {"introduce": introduce},
                    city_name
                )
            except Exception as e:
                logging.warning(f"处理美食项失败: {str(e)[:200]}")

    def _go_to_next_page(self):
        """尝试翻页，成功返回True，失败返回False"""
        try:
            # 查找下一页按钮
            next_btn = WebDriverWait(self.driver, 5).until(
                EC.element_to_be_clickable((By.CLASS_NAME, 'nextpage')))

            # 检查是否已到最后一页
            if "disabled" in next_btn.get_attribute("class"):
                return False

            # 滚动到元素并点击
            self.driver.execute_script("arguments[0].scrollIntoView();", next_btn)
            time.sleep(0.5)
            next_btn.click()

            # 等待新页面加载
            WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located((By.CLASS_NAME, "rdetailbox")))
            return True

        except TimeoutException:
            logging.info("未找到下一页按钮，可能已到最后一页")
            return False
        except Exception as e:
            logging.warning(f"翻页失败: {str(e)[:200]}")
            return False

    def _get_delicacy_introduce(self, url):
        """获取美食详细介绍"""
        if not url or 'http' not in url:
            return "无有效详情链接"

        original_window = self.driver.current_window_handle
        try:
            # 在新标签页打开
            self.driver.execute_script(f"window.open('{url}');")
            self.driver.switch_to.window(self.driver.window_handles[-1])

            # 等待介绍内容加载
            try:
                WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, ".infotext, .desc, .introduce, .content")))

                # 尝试多种可能的介绍内容选择器
                for selector in [".infotext", ".desc", ".introduce", ".content"]:
                    try:
                        return self.driver.find_element(By.CSS_SELECTOR, selector).text.strip()
                    except NoSuchElementException:
                        continue

                return "找到详情页但未识别到介绍内容"
            except TimeoutException:
                return "详情页加载超时"
        except Exception as e:
            logging.warning(f"获取介绍失败: {str(e)[:200]}")
            return "获取介绍时出错"
        finally:
            # 关闭详情页标签并返回原窗口
            if len(self.driver.window_handles) > 1:
                self.driver.close()
                self.driver.switch_to.window(original_window)

    def _load_city_page(self, url):
        """加载城市页面"""
        try:
            self.driver.get(url)
            WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located((By.TAG_NAME, 'body')))
        except TimeoutException:
            logging.warning("页面加载超时，尝试刷新...")
            self.driver.refresh()
            WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located((By.TAG_NAME, 'body')))

    def _restart_browser(self):
        """重启浏览器实例"""
        try:
            self.driver.quit()
            self.driver = self._init_driver()
            logging.info("浏览器实例已重启")
        except Exception as e:
            logging.error(f"浏览器重启失败: {e}")
            raise

    def __del__(self):
        if self.driver:
            self.driver.quit()
            logging.info("浏览器已关闭")


if __name__ == "__main__":
    try:
        crawler = DelicacyCrawler()
        crawler.process_cities()
    except KeyboardInterrupt:
        logging.info("用户中断执行")
    except Exception as e:
        logging.error(f"程序异常终止: {str(e)[:200]}")