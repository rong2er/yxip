import requests
import time
import re
import os

# 测试文件 URL 和大小 (减到 10MB 加速测试)
TEST_URL = 'http://ipv4.download.thinkbroadband.com/10MB.zip'
FILE_SIZE = 10485760  # 10MB 字节

# 试的端口列表：HTTP 先 (80,8080,3128)，SOCKS 后 (1080)
PORTS_TO_TRY = [80, 8080, 3128, 1080]
PROXY_SCHEMES = ['http', 'socks5']  # SOCKS5 for 1080

def get_detailed_location(ip):
    """查询 IP 详细地区"""
    try:
        response = requests.get(f'http://ip-api.com/json/{ip}?fields=status,country,regionName,city', timeout=5)
        data = response.json()
        if data['status'] == 'success':
            country = data['country']
            region = data.get('regionName', '')
            city = data.get('city', '')
            return f"{country} {region} {city}".strip()
        return "Unknown"
    except Exception as e:
        print(f"地区查询失败 {ip}: {e}")
        return "Unknown"

def test_speed(ip):
    """测试 IP 下载速度：试多个端口/SOCKS，取第一个成功"""
    for port in PORTS_TO_TRY:
        for scheme in PROXY_SCHEMES if port == 1080 else ['http']:
            proxy_url = f"{scheme}://{ip}:{port}"
            proxies = {
                'http': proxy_url,
                'https': proxy_url
            }
            start_time = time.time()
            downloaded = 0
            try:
                print(f"  试 {proxy_url}...")
                response = requests.get(TEST_URL, proxies=proxies, stream=True, timeout=20)
                response.raise_for_status()
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        downloaded += len(chunk)
                    if downloaded >= FILE_SIZE:
                        break
                end_time = time.time()
                duration = end_time - start_time
                if duration > 0:
                    speed_mbps = (downloaded / duration) / 1048576  # MB/s
                    if speed_mbps > 0:
                        print(f"  成功！速度: {round(speed_mbps, 1)}MB/s")
                        return round(speed_mbps, 1), port, scheme
                break  # 如果下载了但 speed=0，跳下一个
            except Exception as e:
                print(f"  {proxy_url} 失败: {e}")
                continue
    print(f"  所有端口失败: 连接不通")
    return 0.0, None, None

def main():
    if not os.path.exists('ip.txt'):
        print("ip.txt 不存在！")
        return

    with open('ip.txt', 'r', encoding='utf-8') as f:
        lines = [line.strip() for line in f if line.strip() and not line.startswith('#') and not line.startswith('-')]

    if not lines:
        print("ip.txt 中无有效 IP！")
        return

    results = []
    failed_count = 0
    for line in lines:
        # 提取 IP（格式: IP#地区，支持可选端口）
        match = re.match(r'^(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})(?::\d+)?\s*#(.*)$', line)
        if not match:
            print(f"跳过无效行: {line}")
            continue
        ip = match.group(1)
        orig_region = match.group(2)

        # 查询详细地区
        location = get_detailed_location(ip)
        print(f"\n测试 {ip} - 原始地区: {orig_region}, 详细: {location}")

        # 测试速度（多端口）
        speed, used_port, used_scheme = test_speed(ip)
        time.sleep(1)  # API 延时

        if speed > 0:
            port_str = f":{used_port}" if used_port else ""
            scheme_note = f" ({used_scheme})" if used_scheme == 'socks5' else ""
            result = f"{ip}{port_str}#{location}+{speed}MB/s{scheme_note}"
            results.append(result)
            print(f"  -> 成功: {result}")
        else:
            failed_count += 1
            print(f"  -> 失败: 所有端口不通")

    # 写入 speed_ip.txt（所有成功，按速度降序）
    with open('speed_ip.txt', 'w', encoding='utf-8') as f:
        f.write('# IP 带宽测速结果 (所有成功连接 IP，多端口测试)\n')
        f.write('# 生成时间: ' + time.strftime('%Y-%m-%d %H:%M:%S UTC') + '\n')
        f.write(f'# 总测试: {len(lines)}, 成功: {len(results)}, 失败: {failed_count}\n\n')
        for res in sorted(results, key=lambda x: float(x.split('+')[1].split('M')[0]), reverse=True):
            f.write(res + '\n')

    print(f"\n完成！共 {len(results)} 个成功 IP 保存到 speed_ip.txt (失败 {failed_count} 个)")

if __name__ == '__main__':
    main()
