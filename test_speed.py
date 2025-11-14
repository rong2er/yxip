import requests
import time
import re
import os
import subprocess

# CF 官方带宽测试端点 (10MB 随机数据)
TEST_URL = 'https://speed.cloudflare.com/__down?bytes=10485760'  # 10MB
HOST = 'speed.cloudflare.com'
PORT = 443
FILE_SIZE = 10485760  # 字节，用于验证

# 默认端口
DEFAULT_PORT = 8443

# 国家映射：支持 code (US) 和 full name (United States)
EN_TO_CN = {
    # Codes
    'US': '美国',
    'CA': '加拿大',
    'CN': '中国',
    'GB': '英国',
    'DE': '德国',
    'FR': '法国',
    'JP': '日本',
    'AU': '澳大利亚',
    'IN': '印度',
    'BR': '巴西',
    'RU': '俄罗斯',
    'KR': '韩国',
    'NL': '荷兰',
    'SG': '新加坡',
    'HK': '香港',
    'TW': '台湾',
    # Full names (fallback)
    'United States': '美国',
    'Canada': '加拿大',
    'China': '中国',
    'United Kingdom': '英国',
    'Germany': '德国',
    'France': '法国',
    'Japan': '日本',
    'Australia': '澳大利亚',
    'India': '印度',
    'Brazil': '巴西',
    'Russia': '俄罗斯',
    'South Korea': '韩国',
    'Netherlands': '荷兰',
    'Singapore': '新加坡',
    'Hong Kong': '香港',
    'Taiwan': '台湾',
    'Reserved': '预留',
    'Global': '全球',
    'Unknown': '未知'
}

def get_chinese_country(ip):
    """查询 IP 国家（主: ip-api.com；无信息时备用1: ipinfo.io → 备用2: ipgeolocation.io）"""
    session = requests.Session()  # Session 保持 cookies，模拟浏览器
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Referer': 'https://www.google.com/'  # 模拟来源
    }
    try:
        # 主 API: ip-api.com (HTTPS + 完整 headers)
        url = f'https://ip-api.com/json/{ip}?fields=status,country,countryCode'
        print(f"  查询 {ip} (主 API ip-api.com)...")
        response = session.get(url, headers=headers, timeout=10)
        print(f"  Status: {response.status_code}, Text len: {len(response.text)}")  # 调试
        print(f"  响应预览: {response.text[:50]}...")  # 调试
        
        if response.status_code == 200:
            data = response.json()
            if data.get('status') == 'success':
                en_country = data.get('countryCode') or data.get('country', 'Unknown')  # 优先 code
                if en_country and en_country != 'Unknown':
                    cn_country = EN_TO_CN.get(en_country, en_country)
                    print(f"  国家: {en_country} -> {cn_country}")
                    return cn_country
                else:
                    print("  ip-api.com 无有效信息，尝试备用1...")
        elif response.status_code in [403, 429]:
            print(f"  主 API {response.status_code}，尝试备用1...")
        
        # 备用1: ipinfo.io
        backup1_url = f'https://ipinfo.io/{ip}/country'
        backup1_resp = session.get(backup1_url, headers=headers, timeout=10)
        if backup1_resp.status_code == 200:
            en_country1 = backup1_resp.text.strip()
            if en_country1 and en_country1 != 'Unknown':
                cn_country = EN_TO_CN.get(en_country1, en_country1)
                print(f"  备用1 成功: {en_country1} -> {cn_country}")
                return cn_country
            else:
                print("  ipinfo.io 无有效信息，尝试备用2...")
        else:
            print(f"  备用1 失败: {backup1_resp.status_code}，尝试备用2...")
        
        # 备用2: ipgeolocation.io (demo key)
        backup2_url = f'https://api.ipgeolocation.io/ipgeo?apiKey=demo&ip={ip}&fields=country_code,country_name'
        backup2_resp = session.get(backup2_url, headers=headers, timeout=10)
        if backup2_resp.status_code == 200:
            backup2_data = backup2_resp.json()
            en_country2 = backup2_data.get('country_code') or backup2_data.get('country_name', 'Unknown')
            if en_country2 != 'Unknown':
                cn_country = EN_TO_CN.get(en_country2, en_country2)
                print(f"  备用2 成功: {en_country2} -> {cn_country}")
                return cn_country
            else:
                print("  备用2 也无有效信息")
        else:
            print(f"  备用2 失败: {backup2_resp.status_code}")
    except Exception as e:
        print(f"  异常: {e}")
    
    print(f"  国家查询最终失败 {ip}，默认全球")
    return '全球'

def test_speed(ip, retries=1):
    """用 curl --resolve 测试 CF 带宽 (MB/s)，重试失败"""
    for attempt in range(retries + 1):
        cmd = [
            'curl', '-s',
            '--resolve', f'{HOST}:{PORT}:{ip}',
            TEST_URL,
            '-o', '/dev/null',
            '-w', 'speed_download:%{speed_download}\nsize:%{size_download}\n',
            '--max-time', '30',
            '--connect-timeout', '10',
            '--retry', '1',
            '--insecure'
        ]
        try:
            print(f" 测试 {ip}:443 (尝试 {attempt+1})...")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=40)
            if result.returncode == 0:
                output = result.stdout.strip()
                speed_bps = 0
                downloaded = 0
                for line in output.split('\n'):
                    if line.startswith('speed_download:'):
                        speed_bps = float(line.split(':')[1])
                    elif line.startswith('size:'):
                        downloaded = float(line.split(':')[1])
                if downloaded >= FILE_SIZE * 0.9:
                    speed_mbps = speed_bps / 1048576
                    if speed_mbps > 0:
                        print(f" 成功！下载 {downloaded/1048576:.1f}MB, 速度: {round(speed_mbps, 1)}MB/s")
                        return round(speed_mbps, 1)
                print(f" 下载不完整 (code {result.returncode}): {output}")
                return 0.0
            else:
                print(f" curl 失败 (code {result.returncode}): {result.stderr.strip() if result.stderr else 'Timeout'}")
                if attempt < retries:
                    time.sleep(2)
                else:
                    return 0.0
        except subprocess.TimeoutExpired:
            print(f" curl 超时 (30s)")
            return 0.0
        except Exception as e:
            print(f" curl 异常: {e}")
            return 0.0
    return 0.0

def main():
    print("=== 脚本开始运行 ===")
    try:
        if not os.path.exists('ip.txt'):
            print("ip.txt 不存在！")
            return
        with open('ip.txt', 'r', encoding='utf-8') as f:
            lines = [line.strip() for line in f if line.strip() and not line.startswith('#') and not line.startswith('-')]
        print(f"读取到 {len(lines)} 个 IP")
        if not lines:
            print("ip.txt 中无有效 IP！")
            return
        results = []
        failed_count = 0
        for line in lines:
            # 提取 IP 和可选端口 (格式: IP:PORT#US 或 IP#US)
            match = re.match(r'^(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})(?::(\d+))?\s*#(.*)$', line)
            if not match:
                print(f"跳过无效行: {line}")
                continue
            ip = match.group(1)
            port = match.group(2) or str(DEFAULT_PORT)  # 优先自带端口，没有默认8443
            ip_port = f"{ip}:{port}"
            cn_country = get_chinese_country(ip)
            print(f"\n测试 {ip_port} - {cn_country}")
            speed = test_speed(ip)
            time.sleep(3)  # 延时防限速（加大到3s）
            if speed > 0:
                result = f"{ip_port}#{cn_country} {speed}MB/s"  # 格式: IP:端口#国家 速率
                results.append(result)
                print(f" -> 成功: {result}")
            else:
                failed_count += 1
                print(f" -> 失败: 连接不通")
        # 按速度降序排序，取前 50 个写入 speed_ip.txt
        sorted_results = sorted(results, key=lambda x: float(re.search(r'(\d+\.?\d*)MB/s', x).group(1)), reverse=True)
        top_50 = sorted_results[:50]  # 只取前 50
        with open('speed_ip.txt', 'w', encoding='utf-8') as f:
            for res in top_50:
                f.write(res + '\n')
        print(f"\n完成！共 {len(results)} 个成功 IP，按速度排序后取前 {len(top_50)} 个保存到 speed_ip.txt (失败 {failed_count} 个)")
    except Exception as e:
        print(f"脚本异常: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()
