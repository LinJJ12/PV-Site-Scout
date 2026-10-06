"""
太阳辐射数据获取工具
使用NASA POWER API获取全球太阳辐射数据
"""

import logging
import time

import numpy as np
import requests

logger = logging.getLogger(__name__)


class SolarRadiationAPI:
    """NASA POWER API 封装类

    说明：
    - 使用 Session 复用连接，减少握手开销；
    - NASA POWER 历史数据不会变化，上游调用方应按网格缓存结果，
      避免对同一位置反复请求（官方会限制持续重复请求的客户端）。
    """

    FILL_SENTINELS = (-999.0, -99.0)

    # 各要素的物理合理范围，用于剔除填充值与异常值
    PHYSICAL_BOUNDS = {
        "ALLSKY_SFC_SW_DWN": (0.0, 40.0),   # 日 GHI，kWh/m²/day
        "T2M": (-90.0, 60.0),               # 2m 气温，°C
        "PRECTOTCORR": (0.0, 2000.0),       # 日降水，mm
        "PRECTOT": (0.0, 2000.0),
    }

    def __init__(self):
        self.base_url = "https://power.larc.nasa.gov/api/temporal/daily/point"
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "PV-Site-Scout/1.0 (educational; +https://github.com/LinJJ12/PV-Site-Scout)",
                "Accept": "application/json",
            }
        )

    @classmethod
    def _clean_series(cls, values, low, high):
        """剔除填充值（-999/-99）、null 与超出物理范围的数据点。"""
        cleaned = []
        for value in values:
            if value is None:
                continue
            try:
                number = float(value)
            except (TypeError, ValueError):
                continue
            if np.isfinite(number) and low <= number <= high:
                cleaned.append(number)
        return cleaned

    def get_solar_data(self, lat, lon, start_year=2020, end_year=2023):
        """
        获取指定位置的太阳辐射数据

        Parameters:
        -----------
        lat : float
            纬度
        lon : float
            经度
        start_year : int
            开始年份
        end_year : int
            结束年份

        Returns:
        --------
        dict : 包含GHI, 温度, 降水等指标的年均值；失败时返回 None
        """

        params = {
            'parameters': 'ALLSKY_SFC_SW_DWN,T2M,PRECTOTCORR',  # GHI, 温度, 降水
            'community': 'RE',
            'longitude': lon,
            'latitude': lat,
            'start': f'{start_year}0101',
            'end': f'{end_year}1231',
            'format': 'JSON'
        }

        try:
            response = self.session.get(self.base_url, params=params, timeout=(10, 30))
            response.raise_for_status()
            data = response.json()

            properties = data['properties']['parameter']

            ghi_values = self._clean_series(
                properties.get('ALLSKY_SFC_SW_DWN', {}).values(),
                *self.PHYSICAL_BOUNDS["ALLSKY_SFC_SW_DWN"],
            )
            temp_values = self._clean_series(
                properties.get('T2M', {}).values(),
                *self.PHYSICAL_BOUNDS["T2M"],
            )
            # 部分区域/时段仍返回旧参数名 PRECTOT，做兼容回退
            precip_raw = properties.get('PRECTOTCORR')
            precip_key = 'PRECTOTCORR'
            if not precip_raw:
                precip_raw = properties.get('PRECTOT')
                precip_key = 'PRECTOT'
            precip_values = self._clean_series(
                (precip_raw or {}).values(),
                *self.PHYSICAL_BOUNDS[precip_key],
            )

            if not ghi_values or not temp_values or not precip_values:
                logger.warning("API返回无效气候序列 (%s, %s)", lat, lon)
                return None

            # 计算年份数
            num_years = end_year - start_year + 1

            result = {
                'ghi_annual_mean': float(np.mean(ghi_values)),  # kWh/m²/day
                'ghi_annual_std': float(np.std(ghi_values)),
                'temp_annual_mean': float(np.mean(temp_values)),  # °C
                'temp_annual_std': float(np.std(temp_values)),
                'precip_annual_mean': float(np.sum(precip_values) / num_years),  # mm/year
            }
            if not all(np.isfinite(v) for v in result.values()):
                logger.warning("API统计结果含 NaN/Inf (%s, %s)", lat, lon)
                return None
            return result

        except Exception as e:
            logger.warning("API请求失败 (%s, %s): %s", lat, lon, e)
            return None

    def batch_get_solar_data(self, coordinates, delay=0.5):
        """
        批量获取多个位置的太阳辐射数据

        Parameters:
        -----------
        coordinates : list of tuples
            [(lat1, lon1), (lat2, lon2), ...]
        delay : float
            请求间隔时间(秒)，避免API限流

        Returns:
        --------
        pd.DataFrame : 包含所有位置数据的DataFrame
        """
        import pandas as pd

        results = []
        total = len(coordinates)

        print(f"开始获取 {total} 个位置的太阳辐射数据...")

        for i, (lat, lon) in enumerate(coordinates):
            print(f"进度: {i+1}/{total} ({(i+1)/total*100:.1f}%)", end='\r')

            data = self.get_solar_data(lat, lon)

            if data:
                data['lat'] = lat
                data['lon'] = lon
                results.append(data)

            # 避免API限流
            if i < total - 1:
                time.sleep(delay)

        print(f"\n✓ 完成! 成功获取 {len(results)}/{total} 个位置的数据")

        return pd.DataFrame(results)


# 使用示例
if __name__ == "__main__":

    # 初始化API
    api = SolarRadiationAPI()

    # 单个位置测试
    print("="*60)
    print("单点测试: 北京 (39.9°N, 116.4°E)")
    print("="*60)

    data = api.get_solar_data(lat=39.9, lon=116.4)

    if data:
        print(f"\n年均GHI: {data['ghi_annual_mean']:.2f} kWh/m²/day")
        print(f"年均温度: {data['temp_annual_mean']:.2f} °C")
        print(f"年均降水量: {data['precip_annual_mean']:.2f} mm/year")

    # 批量测试 (示例: 3个城市)
    print("\n" + "="*60)
    print("批量测试: 3个城市")
    print("="*60)

    coords = [
        (39.9, 116.4),   # 北京
        (31.2, 121.5),   # 上海
        (23.1, 113.3),   # 广州
    ]

    df = api.batch_get_solar_data(coords, delay=1.0)

    print("\n结果预览:")
    print(df)

    # 保存结果
    df.to_csv('solar_radiation_sample.csv', index=False)
    print("\n✓ 结果已保存到: solar_radiation_sample.csv")
