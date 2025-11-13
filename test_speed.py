import requests
import time
import re
import os
import subprocess
import json

# CF 官方带宽测试端点 (10MB 随机数据)
TEST_URL = 'https://speed.cloudflare.com/__down?bytes=10485760'  # 10MB
HOST = 'speed.cloudflare.com'
PORT = 443
FILE_SIZE = 10485760  # 字节，用于验证

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

def test_speed(ip, retries=1):
    """用 curl --resolve 测试 CF 带宽 (MB/s)，重试失败"""
    for attempt in range(retries + 1):
        cmd = [
            'curl', '-s',
            '--resolve', f'{HOST}:{PORT}:{ip}',
            TEST_URL,
            '-o', '/dev/null',
            '-w', 'speed_download:%{speed_download}\nsize:%{size_download}\n',
            '--max-time', '30',  # 30s 超时 (大文件)
            '--connect-timeout', '10',
            '--retry', '1',  # curl 内重试
            '--insecure'  # 忽略 SSL 警告，如果有
        ]
        try:
            print(f"  测试 {ip}:443 (尝试 {attempt+1})...")
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
                if downloaded >= FILE_SIZE * 0.9:  # 至少下载 90%
                    speed_mbps = speed_bps / 1048576  # MB/s
                    if speed_mbps > 0:
                        print(f"  成功！下载 {downloaded/1048576:.1f}MB, 速度: {round(speed_mbps, 1)}MB/s")
                        return round(speed_mbps, 1)
                print(f"  下载不完整 (code {result.returncode}): {output}")
                return 0.0
            else:
                print(f"  curl 失败 (code {result.returncode}): {result.stderr.strip() if result.stderr else 'Timeout'}")
                if attempt < retries:
                    time.sleep(2)
                else:
                    return 0.0
        except subprocess.TimeoutExpired:
            print(f"  curl 超时 (30s)")
            return 0.0
        except Exception as e:
            print(f"  curl 异常: {e}")
            return 0.0
    return 0.0

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
        # 提取 IP (格式: IP#US)
        match = re.match(r'^(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})(?::\d+)?\s*#(.*)$', line)
        if not match:
            print(f"跳过无效行: {line}")
            continue
        ip = match.group(1)

        # 查询地区
        location = get_detailed_location(ip)
        print(f"\n测试 {ip} - 详细地区: {location}")

        # 测试带宽
        speed = test_speed(ip)
        time.sleep(1)  # 率限

        if speed > 0:
            result = f"{ip}#{location}+{speed}MB/s"
            results.append(result)
            print(f"  -> 成功: {result}")
        else:
            failed_count += 1
            print(f"  -> 失败: 连接不通")

    # 写入 speed_ip.txt (所有成功，按速降序)
    with open('speed_ip.txt', 'w', encoding='utf-8') as f:
        f.write('# IP 带宽测速结果 (CF 10MB 测试，所有成功 IP)\n')
        f.write('# 生成时间: ' + time.strftime('%Y-%m-%d %H:%M:%S UTC') + '\n')
        f.write(f'# 总测试: {len(lines)}, 成功: {len(results)}, 失败: {failed_count}\n\n')
        for res in sorted(results, key=lambda x: float(x.split('+')[1].replace('MB/s', '')), reverse=True):
            f.write(res + '\n')

    print(f"\n完成！共 {len(results)} 个成功 IP 保存到 speed_ip.txt (失败 {failed_count} 个)")

if __name__ == '__main__':
    main()
