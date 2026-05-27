import json
import sys
import urllib.request
import urllib.error

BASE = 'http://127.0.0.1:8042'

def get_json(path):
    with urllib.request.urlopen(BASE + path, timeout=5) as r:
        return json.loads(r.read().decode('utf-8'))

def post_json(path, payload):
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(BASE + path, data=data, headers={'Content-Type':'application/json'}, method='POST')
    with urllib.request.urlopen(req, timeout=8) as r:
        return json.loads(r.read().decode('utf-8')) if r.readable() else {}

def main():
    ok = True
    print('=== ORTHANC VOLUSON QUICK CHECK ===')

    try:
        system = get_json('/system')
        print(f"[OK] system: {system.get('Name','?')} | DICOM {system.get('DicomPort')} | HTTP {system.get('HttpPort')}")
    except Exception as e:
        print(f"[ERR] system check failed: {e}")
        return 2

    try:
        plugins = get_json('/plugins')
        has_wl = 'orthanc-worklists' in plugins
        print(f"[{'OK' if has_wl else 'ERR'}] orthanc-worklists plugin: {has_wl}")
        ok = ok and has_wl
    except Exception as e:
        print(f"[ERR] plugin check failed: {e}")
        ok = False

    try:
        wls = get_json('/worklists')
        print(f"[OK] worklists count: {len(wls)}")
    except Exception as e:
        print(f"[ERR] worklists endpoint failed: {e}")
        ok = False

    try:
        ch = get_json('/changes?limit=40')
        changes = ch.get('Changes', [])
        last_from_voluson = None
        for c in reversed(changes):
            if c.get('ChangeType') == 'NewInstance':
                iid = c.get('ID')
                try:
                    meta = get_json(f'/instances/{iid}/metadata?expand')
                    if str(meta.get('RemoteIP','')) == '192.168.1.20' or str(meta.get('RemoteAET','')).lower() == 'voluson':
                        last_from_voluson = {
                            'instance': iid,
                            'date': c.get('Date'),
                            'remote_aet': meta.get('RemoteAET'),
                            'remote_ip': meta.get('RemoteIP')
                        }
                        break
                except Exception:
                    pass
        if last_from_voluson:
            print(f"[OK] last Voluson instance: {last_from_voluson['instance']} @ {last_from_voluson['date']} from {last_from_voluson['remote_aet']} ({last_from_voluson['remote_ip']})")
        else:
            print('[WARN] no recent Voluson instance found in last 40 changes')
    except Exception as e:
        print(f"[ERR] change stream check failed: {e}")
        ok = False

    try:
        payload = {'Level':'Series','Query':{'Modality':'SR'},'Limit':1}
        body = post_json('/tools/find', payload)
        count = 0
        if isinstance(body, list):
            count = len(body)
        elif isinstance(body, dict):
            if 'Count' in body:
                count = body.get('Count', 0)
            elif 'value' in body and isinstance(body['value'], list):
                count = len(body['value'])
        print(f"[OK] report(SR) series count: {count}")
    except Exception as e:
        print(f"[ERR] SR/report check failed: {e}")
        ok = False

    print('=== RESULT ===')
    if ok:
        print('ORTHANC_VOLUSON_CHECK_OK')
        return 0
    print('ORTHANC_VOLUSON_CHECK_WARN')
    return 1

if __name__ == '__main__':
    sys.exit(main())
