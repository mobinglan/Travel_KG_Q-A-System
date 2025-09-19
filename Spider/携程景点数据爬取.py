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
        logging.FileHandler('travel_crawler.log'),
        logging.StreamHandler()
    ]
)


class Neo4jClient:
    def __init__(self, uri, user, password):
        self.graph = Graph(uri, auth=(user, password))
        self._setup_constraints()
        self.current_batch = []
        self.batch_size = 20
        self.special_cities = {"北京", "天津", "上海", "重庆", "香港", "澳门", "台湾"}

    def _setup_constraints(self):
        try:
            self.graph.run("CREATE CONSTRAINT IF NOT EXISTS FOR (p:Province) REQUIRE p.name IS UNIQUE")
            self.graph.run("CREATE CONSTRAINT IF NOT EXISTS FOR (c:City) REQUIRE c.name IS UNIQUE")
            self.graph.run(
                "CREATE CONSTRAINT IF NOT EXISTS FOR (s:Sight) REQUIRE s.city_uid IS UNIQUE")  # 修改为city_uid唯一
        except Exception as e:
            logging.warning(f"约束可能已存在: {str(e)[:200]}")
    def create_province(self, province_data):
        try:
            province = Node("Province", **self._clean_data(province_data))
            self.graph.merge(province, "Province", "name")
            return province
        except Exception as e:
            logging.error(f"创建省份节点失败: {e}")
            return None

    def create_city(self, city_data, province_node=None):
        try:
            city = Node("City", **self._clean_data(city_data))
            self.graph.merge(city, "City", "name")

            if province_node:
                rel = Relationship(city, "BELONGS_TO", province_node)
                self.graph.merge(rel)

            return city
        except Exception as e:
            logging.error(f"创建城市节点失败: {e}")
            return None
    def create_sight(self, sight_data, detail_data, city_node):
        try:
            # 生成唯一标识：城市名+景点名
            uid = f"{city_node['name']}_{sight_data.get('name', '')}"

            combined = self._clean_data({
                **sight_data,
                **detail_data,
                "city_uid": uid,  # 新增唯一标识字段
                "city": city_node["name"],
                "city_url": city_node["url"]
            })

            if self._sight_exists(uid):  # 改为通过city_uid检查
                logging.info(f"跳过已存在景点: {uid}")
                return None

            self.current_batch.append((combined, city_node))
            if len(self.current_batch) >= self.batch_size:
                self._commit_batch()
            return combined
        except Exception as e:
            logging.error(f"准备景点数据失败: {e}")
            return None

    def _sight_exists(self, uid):
        """通过city_uid检查景点是否存在"""
        query = "MATCH (s:Sight {city_uid: $uid}) RETURN s LIMIT 1"
        return bool(self.graph.run(query, uid=uid).data())

    def _commit_batch(self):
        if not self.current_batch:
            return

        tx = self.graph.begin()
        try:
            for data, city_node in self.current_batch:
                sight = Node("Sight", **data)
                tx.create(sight)

                rel = Relationship(sight, "LOCATED_IN", city_node)
                tx.create(rel)

                if data.get("features"):
                    for feature in data["features"].split():
                        feature_node = Node("Feature", name=feature.strip())
                        tx.merge(feature_node, "Feature", "name")
                        tx.create(Relationship(sight, "HAS_FEATURE", feature_node))

            tx.commit()
            logging.info(f"成功提交 {len(self.current_batch)} 个景点")
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


class TravelCrawler:
    def __init__(self):
        self.driver = self._init_driver()
        self.neo4j = Neo4jClient("bolt://localhost:7687", "neo4j", "mo301329")
        self.processed = 0
        self.errors = 0

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

    def process_cities(self):
        with open("D:/旅游知识图谱/完整的/Sight_citys01 .txt", 'r', encoding='utf-8') as f:
            cities = json.load(f)

        for idx, city in enumerate(cities):
            try:
                if idx % 3 == 0:
                    self._restart_browser()

                if city['city_name'] in self.neo4j.special_cities:
                    self._process_special_city(city)
                else:
                    self._process_province(city)

                self.processed += 1
            except Exception as e:
                self.errors += 1
                logging.error(f"处理失败 [{city.get('city_name')}]: {str(e)[:200]}")

        self.neo4j._commit_batch()
        logging.info(f"处理完成！成功：{self.processed} 失败：{self.errors}")

    def _process_special_city(self, city_data):
        """处理特殊城市（直接处理当前页面）"""
        logging.info(f"处理特殊城市: {city_data['city_name']}")
        city_node = self.neo4j.create_city({
            "name": city_data["city_name"],
            "url": city_data["city_url"]
        })

        try:
            self.driver.get(city_data["city_url"])
            self._process_city_content(city_node)
        except Exception as e:
            logging.error(f"特殊城市处理失败: {str(e)[:200]}")
            self._restart_browser()

    def _restart_browser(self):
        try:
            self.driver.quit()
            self.driver = self._init_driver()
            logging.info("浏览器实例已重启")
        except Exception as e:
            logging.error(f"浏览器重启失败: {e}")
            raise
    def _process_province(self, province_data):
        """处理省份"""
        logging.info(f"处理省份: {province_data['city_name']}")
        province_node = self.neo4j.create_province({
            "name": province_data["city_name"],
            "url": province_data["city_url"]
        })
        self._load_province_page(province_data["city_url"], province_node)

    def _load_province_page(self, url, province_node):
        """处理省份下属城市"""
        try:
            self.driver.get(url)
            WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located((By.CLASS_NAME, 'districtFilter_cityBox__o_JaB')))

            # 获取城市元素（跳过第一个"全部"）
            city_elements = self.driver.find_elements(
                By.XPATH, '//div[@class="districtFilter_cityBox__o_JaB"]/div')[1:]

            for element in city_elements:
                city_name = element.text.strip()
                if not city_name:
                    continue

                # 创建城市节点
                city_node = self.neo4j.create_city({
                    "name": city_name,
                    "url": self.driver.current_url
                }, province_node)

                # 点击城市触发动态加载
                element.click()
                time.sleep(5)  # 等待动画效果

                try:
                    # 等待数据刷新
                    WebDriverWait(self.driver, 15).until(
                        EC.presence_of_element_located((By.CLASS_NAME, "baseInfoModule_box__r0bkr")))

                    # 处理当前城市内容
                    self._process_city_content(city_node)
                except TimeoutException:
                    logging.warning(f"城市 {city_name} 数据加载超时")

        except Exception as e:
            logging.error(f"省份处理失败: {str(e)[:200]}")
            self._restart_browser()


    def _process_city_content(self, city_node):
        """通用城市内容处理（含翻页）"""
        try:
            page_count = 1
            while page_count <= 2:
                logging.info(f"正在处理第 {page_count} 页")
                if not self._process_current_page(city_node):
                    break

                if not self._go_to_next_page():
                    break

                page_count += 1
                time.sleep(random.uniform(1, 3))
        except Exception as e:
            logging.error(f"城市内容处理失败: {str(e)[:200]}")
        finally:
            self.neo4j._commit_batch()


    def _process_current_page(self, city_node):
        try:
            elements = WebDriverWait(self.driver, 20).until(
                EC.presence_of_all_elements_located((By.CLASS_NAME, "baseInfoModule_box__r0bkr")))

            for element in elements:
                try:
                    sight_data = self._extract_basic_info(element)
                    detail_data = self._extract_detail_info(element)
                    if sight_data.get("name"):
                        self.neo4j.create_sight(sight_data, detail_data, city_node)
                except Exception as e:
                    logging.warning(f"景点处理失败: {str(e)[:200]}")

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
            name_elem = element.find_element(By.XPATH, './/div[@class="titleModule_name__Li4Tv"]/span/a')
            data["name"] = name_elem.text
            data["url"] = name_elem.get_attribute('href')

            data["star"] = self._safe_extract(
                element,
                './/div[@class="titleModule_name__Li4Tv"]/span[2]',
                "无等级")

            fields = {
                "position": (By.XPATH, './/div[@class="distanceView_box__zWu29"]'),
                "price": (By.XPATH, './/div[@class="priceView_real-price-view__l7J6R"]'),
                "heat": (By.XPATH, './/div[@class="commentInfoModule_heat-score-view__yL8zo"]/span[2]'),
                "comment_score": (By.XPATH, './/div[@class="commentInfoModule_comment-view__LBx9p"]/span[2]'),
                "comment_number": (By.XPATH, './/div[@class="commentInfoModule_comment-view__LBx9p"]/span[3]'),
                "features": (By.XPATH, './/div[@class="rankInfoModule_box__hYVJR"]')
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
            link = element.find_element(By.XPATH, './/div[@class="titleModule_name__Li4Tv"]/span/a')
            self.driver.execute_script("arguments[0].click();", link)
            WebDriverWait(self.driver, 10).until(EC.number_of_windows_to_be(2))
            self.driver.switch_to.window(self.driver.window_handles[-1])

            detail_fields = {
                "address": (By.XPATH, '//*/div[@class="baseInfoContent"]/div[1]/p[2]'),
                "open_time": (By.XPATH, '//*/p[@class="baseInfoText cursor openTimeText"]'),
                "phone_number": (By.XPATH, '//*/div[@class="baseInfoText phoneHeaderBox"]'),
                "introduction": (By.XPATH, '//*[@id="__next"]/div[3]/div/div[4]/div[1]/div[2]/div/div[2]/div'),
                "open_hours": (By.XPATH, '//*[@id="__next"]/div[3]/div/div[4]/div[1]/div[2]/div/div[4]'),
                "preferential": (By.XPATH,
                                 '//div[@class="moduleContent"][preceding-sibling::div[@class="moduleTitle" and text()="优待政策"]]'),
                "facilities": (By.XPATH,
                               '//div[@class="moduleContent"][preceding-sibling::div[@class="moduleTitle" and text()="服务设施"]]'),
                "remind": (By.XPATH,
                           '//div[@class="moduleContent"][preceding-sibling::div[@class="moduleTitle" and text()="必看贴士"]]')
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
                EC.element_to_be_clickable((By.CSS_SELECTOR, 'li.ant-pagination-next')))

            if "disabled" in next_btn.get_attribute("class"):
                return False

            self.driver.execute_script("arguments[0].scrollIntoView();", next_btn)
            time.sleep(0.5)
            self.driver.execute_script("arguments[0].click();", next_btn)
            WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".baseInfoModule_box__r0bkr")))
            return True
        except Exception as e:
            logging.warning(f"翻页失败: {str(e)[:200]}")
            return False




    def __del__(self):
        if self.driver:
            self.driver.quit()
            logging.info("浏览器已关闭")


if __name__ == "__main__":
    try:
        crawler = TravelCrawler()
        crawler.process_cities()
    except KeyboardInterrupt:
        logging.info("用户中断执行")
    except Exception as e:
        logging.error(f"程序异常终止: {str(e)[:200]}")


        #黑龙缉3