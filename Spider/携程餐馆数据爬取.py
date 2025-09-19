from py2neo import Graph, Node, Relationship
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver import ChromeOptions
from selenium.common.exceptions import TimeoutException
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
        logging.FileHandler('restaurant_crawler.log'),
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
        """约束设置优化"""
        try:
            self.graph.run("CREATE CONSTRAINT IF NOT EXISTS FOR (c:City) REQUIRE c.name IS UNIQUE")
            self.graph.run("CREATE CONSTRAINT IF NOT EXISTS FOR (r:Restaurant) REQUIRE r.city_uid IS UNIQUE")
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

    def create_restaurant(self, restaurant_data, detail_data, city_name):
        """创建餐馆节点（关联现有城市）"""
        try:
            city_node = self.get_city_node(city_name)
            if not city_node:
                logging.error(f"城市节点不存在: {city_name}")
                return None

            # 生成唯一标识
            uid = f"{city_name}_{restaurant_data.get('name', '')}"

            combined = self._clean_data({
                **restaurant_data,
                **detail_data,
                "city_uid": uid,
                "city": city_name,
                "city_url": city_node["url"]  # 使用城市真实URL
            })

            if self._restaurant_exists(uid):
                logging.info(f"跳过已存在餐馆: {uid}")
                return None

            self.current_batch.append((combined, city_node))

            if len(self.current_batch) >= self.batch_size:
                self._commit_batch()

            return combined
        except Exception as e:
            logging.error(f"准备餐馆数据失败: {e}")
            return None

    def _restaurant_exists(self, uid):
        """基于唯一标识检查存在性"""
        query = "MATCH (r:Restaurant {city_uid: $uid}) RETURN r LIMIT 1"
        return bool(self.graph.run(query, uid=uid).data())

    def _commit_batch(self):
        """批量提交优化"""
        if not self.current_batch:
            return

        tx = self.graph.begin()
        try:
            for data, city_node in self.current_batch:
                restaurant = Node("Restaurant", **data)
                tx.create(restaurant)

                # 创建关系
                rel = Relationship(restaurant, "LOCATED_IN", city_node)
                tx.create(rel)

                # 菜系关系
                if data.get("cooking_style"):
                    for style in data["cooking_style"].split():
                        style_node = Node("Cooking_Style", name=style.strip())
                        tx.merge(style_node, "Cooking_Style", "name")
                        tx.create(Relationship(restaurant, "HAS_STYLE", style_node))

            tx.commit()
            logging.info(f"成功提交 {len(self.current_batch)} 个餐馆")
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


class RestaurantCrawler:
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
            with open("D:/旅游知识图谱/完整的/Restaurant_citys.txt", 'r', encoding='utf-8') as f:
                cities = json.load(f)

            valid_data = [c for c in cities if c['city_name'] in self.valid_cities]
            logging.info(f"有效城市数量: {len(valid_data)}/{len(cities)}")

            for idx, city in enumerate(valid_data):
                try:
                    if idx % 3 == 0:
                        self._restart_browser()

                    self._process_city(city['city_name'], city['restaurant_url'])
                    self.processed += 1
                except Exception as e:
                    self.errors += 1
                    logging.error(f"处理失败 [{city.get('city_name')}]: {str(e)[:200]}")

            self.neo4j._commit_batch()
            logging.info(f"处理完成！成功：{self.processed} 失败：{self.errors}")
        except Exception as e:
            logging.error(f"文件处理失败: {str(e)}")

    def _process_city(self, city_name, city_url):
        logging.info(f"开始处理城市: {city_name}")
        try:
            self._load_city_page(city_url)
            page_count = 1

            while page_count <= 2:
                logging.info(f"正在处理第 {page_count} 页")
                if not self._process_current_page(city_name):
                    break
                if not self._go_to_next_page():
                    break
                page_count += 1
                time.sleep(random.uniform(1, 3))
        finally:
            self.neo4j._commit_batch()

    def _load_city_page(self, url):
        try:
            self.driver.get(url)
            WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located((By.CLASS_NAME, "rdetailbox")))
        except TimeoutException:
            logging.warning("页面加载超时，尝试刷新...")
            self.driver.refresh()
            WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located((By.TAG_NAME, 'body')))

    def _process_current_page(self, city_name):
        try:
            self.driver.execute_script(
                "window.scrollTo(0, Math.random() * document.body.scrollHeight)")
            time.sleep(0.5)

            elements = WebDriverWait(self.driver, 20).until(
                EC.presence_of_all_elements_located((By.CLASS_NAME, "rdetailbox")))

            for element in elements:
                try:
                    restaurant_data = self._extract_basic_info(element)
                    detail_data = self._extract_detail_info(element)
                    if restaurant_data.get("name"):
                        self.neo4j.create_restaurant(restaurant_data, detail_data, city_name)
                except Exception as e:
                    logging.warning(f"餐馆处理失败: {str(e)[:200]}")
            return True
        except TimeoutException:
            logging.error("等待元素超时")
            return False
        except Exception as e:
            logging.error(f"页面处理失败: {str(e)[:200]}")
            return False

    def _extract_basic_info(self, element):
        data = {}
        try:
            name_elem = element.find_element(By.XPATH, './/dl/dt/a')
            data["name"] = name_elem.text
            data["url"] = name_elem.get_attribute('href')

            fields = {
                "comment_score": (By.XPATH, './/ul[@class="r_comment"]/li[1]/a/strong'),
                "comment_number": (By.XPATH, './/ul[@class="r_comment"]/li[3]/a')
            }
            for key, locator in fields.items():
                data[key] = self._safe_extract(element, locator)
            return data
        except Exception as e:
            logging.warning(f"基础信息提取失败: {str(e)[:200]}")
            return {}

    def _extract_detail_info(self, element):
        detail = {}
        original_window = self.driver.current_window_handle
        try:
            link = element.find_element(By.XPATH, './/dl/dt/a')
            self.driver.execute_script("arguments[0].click();", link)
            WebDriverWait(self.driver, 10).until(EC.number_of_windows_to_be(2))
            self.driver.switch_to.window(self.driver.window_handles[-1])

            detail_fields = {
                "price_average": (By.XPATH, '//*/ul[@class="s_sight_in_list s_sight_noline cf"]/li[1]/span[2]/em'),
                "cooking_style": (By.XPATH, '//*/ul[@class="s_sight_in_list s_sight_noline cf"]/li[2]/span[2]/dd/a'),
                "phone_number": (By.XPATH, '//*/ul[@class="s_sight_in_list s_sight_noline cf"]/li[3]/span[2]'),
                "address": (By.XPATH, '//*/ul[@class="s_sight_in_list s_sight_noline cf"]/li[4]/span[2]'),
                "open_hours": (By.XPATH, '//*/ul[@class="s_sight_in_list s_sight_noline cf"]/li[5]/span[2]'),
                "introduction": (By.XPATH, '//*[@id="content"]/div[3]/div/div[1]/div[3]/div[1]/div[1]'),
                "cuisine": (By.XPATH, '//*[@id="content"]/div[3]/div/div[1]/div[3]/div[1]/div[2]/p'),
                "taste_score": (By.XPATH, '//*[@class="comment_show"]/dd[1]/span[3]'),
                "environmental_score": (By.XPATH, '//*[@class="comment_show"]/dd[2]/span[3]'),
                "service_score": (By.XPATH, '//*[@class="comment_show"]/dd[3]/span[3]')
            }

            for key, locator in detail_fields.items():
                detail[key] = self._safe_extract_detail(locator)
            return detail
        except Exception as e:
            logging.warning(f"详情提取失败: {str(e)[:200]}")
            return {}
        finally:
            try:
                self.driver.close()
                self.driver.switch_to.window(original_window)
            except:
                self._restart_browser()

    def _safe_extract(self, element, locator, default=""):
        try:
            if isinstance(locator, tuple):
                by, value = locator
                return element.find_element(by, value).text
            return element.find_element(By.XPATH, locator).text
        except:
            return default

    def _safe_extract_detail(self, locator, default="无信息"):
        try:
            return WebDriverWait(self.driver, 5).until(
                EC.visibility_of_element_located(locator)
            ).text
        except:
            return default

    def _go_to_next_page(self):
        try:
            next_btn = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.CLASS_NAME, 'nextpage')))
            if "disabled" in next_btn.get_attribute("class"):
                return False

            self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", next_btn)
            time.sleep(0.5)
            self.driver.execute_script("arguments[0].click();", next_btn)
            WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located((By.CLASS_NAME, "rdetailbox")))
            return True
        except Exception as e:
            logging.warning(f"翻页失败: {str(e)[:200]}")
            return False

    def _restart_browser(self):
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
        crawler = RestaurantCrawler()
        crawler.process_cities()
    except KeyboardInterrupt:
        logging.info("用户中断执行")
    except Exception as e:
        logging.error(f"程序异常终止: {str(e)[:200]}")



        # 昌都