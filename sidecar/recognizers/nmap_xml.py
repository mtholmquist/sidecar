import xml.etree.ElementTree as ET
from typing import Dict, Any

def parse_nmap_xml(path: str) -> Dict[str, Any]:
    facts = {"open_tcp": [], "open_udp": [], "hosts": []}
    try:
        tree = ET.parse(path); root = tree.getroot()
        for host in root.findall(".//host"):
            addr = host.find("./address"); ip = addr.get("addr") if addr is not None else None
            if ip and ip not in facts["hosts"]: facts["hosts"].append(ip)
            for port in host.findall(".//ports/port"):
                proto = port.get("protocol",""); pno = int(port.get("portid","0"))
                state = port.find("./state")
                if state is None or state.get("state") != "open": continue
                svc = port.find("./service")
                service = (svc.get("name") if svc is not None else "") or ""
                product = (svc.get("product") if svc is not None else "") or ""
                rec = {"host": ip, "port": pno, "service": service, "product": product}
                if proto == "tcp": facts["open_tcp"].append(rec)
                else: facts["open_udp"].append(rec)
    except Exception as e:
        facts["error"] = str(e)
    return facts
