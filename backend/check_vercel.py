import urllib.request, re
try:
    html = urllib.request.urlopen('https://certificate-generator-app-iste.vercel.app').read().decode('utf-8')
    js_files = re.findall(r'src="(/assets/index-[^"]+\.js)"', html)
    if not js_files:
        print("No JS file found")
        exit()
    js_code = urllib.request.urlopen('https://certificate-generator-app-iste.vercel.app' + js_files[0]).read().decode('utf-8')
    render = re.findall(r'https://certificate-generator-app-dlh6.onrender.com[^\'"]*', js_code)
    local = re.findall(r'http://localhost:\d+[^\'"]*', js_code)
    print("Render matches:", set(render))
    print("Local matches:", set(local))
except Exception as e:
    print("Error:", e)
