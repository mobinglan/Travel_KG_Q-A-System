import pandas as pd
from py2neo import Graph, Node, Relationship
import logging
from tqdm import tqdm
import warnings

warnings.filterwarnings('ignore')

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('metro_import.log'),
        logging.StreamHandler()
    ]
)

# Neo4j约束设置
CONSTRAINTS = [
    "CREATE CONSTRAINT IF NOT EXISTS FOR (c:City) REQUIRE c.name IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (d:District) REQUIRE d.name IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (l:Line) REQUIRE l.city_uid IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (s:Station) REQUIRE s.poi_id IS UNIQUE"
]


class MetroDataImporter:
    def __init__(self, neo4j_uri, neo4j_user, neo4j_password):
        """
        初始化Neo4j连接
        :param neo4j_uri: Neo4j数据库地址，如"bolt://localhost:7687"
        :param neo4j_user: 用户名
        :param neo4j_password: 密码
        """
        self.graph = Graph(neo4j_uri, auth=(neo4j_user, neo4j_password))
        self._setup_constraints()
        self.batch_size = 500  # 每批处理500条记录
        self.current_batch = []
        self.stats = {
            'cities': set(),
            'districts': set(),
            'lines': set(),
            'stations': set()
        }

    def _setup_constraints(self):
        """设置Neo4j唯一约束"""
        for constraint in CONSTRAINTS:
            try:
                self.graph.run(constraint)
                logging.info(f"约束设置成功: {constraint}")
            except Exception as e:
                logging.warning(f"约束可能已存在: {str(e)[:200]}")

    def import_from_excel(self, file_path, sheet_name=0):
        """
        从Excel文件导入地铁数据
        :param file_path: Excel文件路径
        :param sheet_name: 工作表名或索引，默认为第一个工作表
        """
        try:
            # 读取Excel数据
            df = pd.read_excel(file_path, sheet_name=sheet_name)
            logging.info(f"成功读取Excel文件，共 {len(df)} 条记录")

            # 数据预处理
            df = self._preprocess_data(df)

            # 使用进度条显示处理进度
            with tqdm(total=len(df), desc="导入进度") as pbar:
                for _, row in df.iterrows():
                    try:
                        self._process_row(row)
                        pbar.update(1)

                        # 批量提交
                        if len(self.current_batch) >= self.batch_size:
                            self._commit_batch()

                    except Exception as e:
                        logging.error(f"处理行失败（行{_ + 2}）: {str(e)[:200]}")

                # 提交剩余数据
                self._commit_batch()

            # 打印导入统计
            self._print_stats()

        except Exception as e:
            logging.error(f"导入失败: {str(e)}")
            raise

    def _preprocess_data(self, df):
        """数据预处理"""
        # 重命名列（兼容不同格式）
        column_map = {
            '站点名称': 'station_name',
            'POI编号': 'poi_id',
            '拼音名称': 'pinyin',
            'gd经度': 'gd_lng',
            'gd纬度': 'gd_lat',
            '路线名称': 'line_name',
            '城市名称': 'city',
            '行政区名称': 'district',
            'bd经度': 'bd_lng',
            'bd纬度': 'bd_lat'
        }
        df = df.rename(columns={k: v for k, v in column_map.items() if k in df.columns})

        # 填充空值
        df = df.where(pd.notnull(df), None)

        # 去除前后空格
        str_cols = ['station_name', 'line_name', 'city', 'district']
        for col in str_cols:
            if col in df.columns:
                df[col] = df[col].str.strip()

        # 过滤无效数据
        required_cols = ['station_name', 'poi_id', 'line_name', 'city']
        df = df.dropna(subset=required_cols, how='any')

        return df

    def _process_row(self, row):
        """处理单行数据"""
        # 创建/更新城市节点
        city_node = Node("City",
                         name=row['city'],
                         gd_lng=row.get('gd_lng'),
                         gd_lat=row.get('gd_lat'),
                         bd_lng=row.get('bd_lng'),
                         bd_lat=row.get('bd_lat'))
        self.graph.merge(city_node, "City", "name")
        self.stats['cities'].add(row['city'])

        # 创建/更新行政区节点（如果存在）
        if row.get('district'):
            district_node = Node("District",
                                 name=row['district'],
                                 city=row['city'])
            self.graph.merge(district_node, "District", "name")
            self.stats['districts'].add(row['district'])

            # 创建行政区-城市关系
            self.current_batch.append(
                Relationship(district_node, "PART_OF", city_node))

        # 创建/更新地铁线路节点
        line_uid = f"{row['city']}_{row['line_name']}"
        line_node = Node("Line",
                         name=row['line_name'],
                         city_uid=line_uid,
                         city=row['city'])
        self.graph.merge(line_node, "Line", "city_uid")
        self.stats['lines'].add(line_uid)

        # 创建线路-城市关系
        self.current_batch.append(
            Relationship(line_node, "OPERATES_IN", city_node))

        # 创建/更新站点节点
        station_node = Node("Station",
                            name=row['station_name'],
                            poi_id=row['poi_id'],
                            pinyin=row.get('pinyin'),
                            gd_lng=row.get('gd_lng'),
                            gd_lat=row.get('gd_lat'),
                            bd_lng=row.get('bd_lng'),
                            bd_lat=row.get('bd_lat'),
                            line_name=row['line_name'],
                            city=row['city'])
        self.graph.merge(station_node, "Station", "poi_id")
        self.stats['stations'].add(row['poi_id'])

        # 创建站点-线路关系
        self.current_batch.append(
            Relationship(station_node, "BELONGS_TO", line_node))

        # 创建站点-城市关系
        self.current_batch.append(
            Relationship(station_node, "LOCATED_IN", city_node))

        # 创建站点-行政区关系（如果存在）
        if row.get('district'):
            self.current_batch.append(
                Relationship(station_node, "LOCATED_IN", district_node))

    def _commit_batch(self):
        """批量提交数据到Neo4j"""
        if not self.current_batch:
            return

        tx = self.graph.begin()
        try:
            for rel in self.current_batch:
                tx.merge(rel)
            tx.commit()
            logging.info(f"已提交 {len(self.current_batch)} 条关系")
            self.current_batch = []
        except Exception as e:
            tx.rollback()
            logging.error(f"批量提交失败: {str(e)[:200]}")
            self.current_batch = []

    def _print_stats(self):
        """打印导入统计信息"""
        stats_msg = """
        ========== 导入统计 ==========
        城市数量: {cities}
        行政区数量: {districts}
        地铁线路数量: {lines}
        站点数量: {stations}
        =============================
        """.format(
            cities=len(self.stats['cities']),
            districts=len(self.stats['districts']),
            lines=len(self.stats['lines']),
            stations=len(self.stats['stations'])
        )
        logging.info(stats_msg)


if __name__ == "__main__":
    # 使用示例
    IMPORTER = MetroDataImporter(
        neo4j_uri="bolt://localhost:7687",
        neo4j_user="neo4j",
        neo4j_password="mo301329"
    )

    # 导入数据（支持.xlsx或.csv）
    IMPORTER.import_from_excel(
        file_path="D:/旅游知识图谱/完整的/地铁.xlsx",
        sheet_name=0  # 可以是工作表名或索引
    )