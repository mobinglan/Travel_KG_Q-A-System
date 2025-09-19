import pandas as pd
import requests as req
from urllib.parse import quote
from tqdm import tqdm
import time
from neo4j import GraphDatabase

# Neo4j connection settings
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "mo301329"

# Tencent Maps API Key
KEY = 'USCBZ-GCTL3-JDB3Z-RXXYD-MYGAS-E3F2R'

# Output Excel file path
OUTPUT_PATH = r"D:/旅游知识图谱/all_sights_coordinates.xlsx"  # Changed filename

# Request limits
SUCCESS_LIMIT = 10000  # Daily quota limit
FAILURE_LIMIT = 20  # Consecutive failure limit

# Request URL prefix
URL_PREFIX = 'https://apis.map.qq.com/ws/geocoder/v1/?address='


def get_cor(address, key):
    """
    Get coordinates for a single address
    :param address: address string
    :param key: Tencent Maps API key
    :return: dictionary with lat/lng coordinates or None if failed
    """
    address_encoded = quote(address)
    url = f'{URL_PREFIX}{address_encoded}&key={key}'
    try:
        response = req.get(url)
        data = response.json()
        if data.get('status') == 0:
            return data.get('result').get('location')
        return None
    except:
        return None

def get_city_sights(uri, user, password, city_name):
    """
    Retrieve sight names and addresses from Neo4j for a specific city
    :return: DataFrame with name, address, price, description, and initial_rating columns
    """
    query = """
    MATCH (s:Sight)-[:LOCATED_IN]->(c:City {name: $city_name})
    WHERE s.address IS NOT NULL AND s.address <> ''
    RETURN s.name AS name, s.address AS address, 
           s.price AS price, s.introduction AS description, 
           s.comment_score AS initial_rating
    """

    with GraphDatabase.driver(uri, auth=(user, password)) as driver:
        with driver.session() as session:
            result = session.run(query, city_name=city_name)
            # Extract results with all fields
            data = [(record["name"], record["address"],
                     record.get("price"),
                     record.get("description"),
                     record.get("initial_rating")) for record in result]


    # Create DataFrame with all columns
    if data:
        df1 = pd.DataFrame(data, columns=["name", "address", "price", "description", "initial_rating"])
        # Add city column
        df1['city'] = city_name

        # Standardize price format
        df1['price'] = df1['price'].apply(
            lambda x: (
                "免费" if pd.isnull(x) or str(x).strip() == "" or "免费" in str(x)
                else f"¥{float(x.split('¥')[-1].replace('起', '').strip())}"
                if "¥" in str(x)
                else f"¥{float(x)}" if str(x).replace('.', '').isdigit()
                else x
            )
        )
        return df1
    return pd.DataFrame()


def load_city_names(file_path):
    """Load city names from text file"""
    with open("D:\旅游知识图谱\All_name_citys.txt", 'r', encoding='utf-8') as f:
        content = f.read()
    # Split by comma and strip whitespace
    cities = [city.strip() for city in content.split(',')]
    return cities


if __name__ == '__main__':
    # Load city names
    city_names = load_city_names('All_name_citys.txt')
    print(f"Found {len(city_names)} cities to process")

    all_dfs = []
    success_count = 0
    failure_count = 0

    # Process each city
    for city in tqdm(city_names, desc="Processing cities"):
        # Get sights for current city
        df_city = get_city_sights(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, city)

        if df_city.empty:
            continue

        # Add columns for coordinates
        df_city['longitude'] = None
        df_city['latitude'] = None

        # Process each sight in the city
        for index, row in df_city.iterrows():
            address = row['address']
            if pd.notnull(address):
                # Add city prefix if not already present
                full_address = address if address.startswith(city) else f'{city}{address}'

                cor = get_cor(full_address, KEY)
                if cor:
                    df_city.at[index, 'longitude'] = cor.get('lng')
                    df_city.at[index, 'latitude'] = cor.get('lat')
                    success_count += 1
                    failure_count = 0
                else:
                    failure_count += 1

            # Rate limiting
            if success_count > 0 and success_count % 5 == 0:
                time.sleep(1)

            # Check limits
            if success_count >= SUCCESS_LIMIT or failure_count >= FAILURE_LIMIT:
                print(f"Stopping early due to limit reached (successes: {success_count}, failures: {failure_count})")
                break

        # Add to combined dataframe
        all_dfs.append(df_city)

    if not all_dfs:
        print("No sights found for any city.")
        exit()

    # Combine all city data
    result_df = pd.concat(all_dfs, ignore_index=True)

    # Filter out records without coordinates
    result_df = result_df.dropna(subset=['longitude', 'latitude'])

    # Save to Excel
    result_df.to_excel(OUTPUT_PATH, index=False)
    print(
        f"Successfully processed {len(result_df)} sights from {len(city_names)} cities. Results saved to {OUTPUT_PATH}")
    print(f"Failed to geocode {sum(len(df) for df in all_dfs) - len(result_df)} addresses.")