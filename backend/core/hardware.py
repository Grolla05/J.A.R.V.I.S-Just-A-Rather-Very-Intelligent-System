import json
import subprocess

from .database import db
from .logger import log


def run_powershell(cmd):
    """Executa um comando PS e retorna o objeto Python (Dict ou List)."""
    try:
        full_cmd = f"powershell -Command \"{cmd} | ConvertTo-Json -Compress\""
        result = subprocess.run(
            full_cmd,
            capture_output=True,
            text=True,
            shell=True
        )
        if result.returncode != 0 or not result.stdout.strip():
            return None
        return json.loads(result.stdout)
    except Exception as e:
        log.error(f"Erro ao executar PowerShell '{cmd}': {e}")
        return None


def scan_system_hardware():
    """
    Executa varredura profunda de hardware via PowerShell
    e popula a tabela 'hardware' do banco de dados.
    """
    log.info("J.A.R.V.I.S. Hardware Scan: Iniciando varredura via PowerShell...")

    cpu_data = run_powershell("Get-CimInstance Win32_Processor | Select-Object Name, MaxClockSpeed, Manufacturer")
    if cpu_data:
        if isinstance(cpu_data, list): cpu_data = cpu_data[0]
        name = cpu_data.get('Name', 'Desconhecido').strip()
        clock = round(cpu_data.get('MaxClockSpeed', 0) / 1000, 2)
        db.update_hardware_spec("Processador (CPU)", f"{name} @ {clock}GHz")

    ram_data = run_powershell("Get-CimInstance Win32_PhysicalMemory | Select-Object Capacity, Speed, Manufacturer")
    if ram_data:
        if not isinstance(ram_data, list): ram_data = [ram_data]
        total_capacity = 0
        details = []
        for stick in ram_data:
            cap_gb = round(stick.get('Capacity', 0) / (1024**3), 2)
            total_capacity += cap_gb
            details.append(f"{cap_gb}GB {stick.get('Manufacturer', '')}")
        db.update_hardware_spec("Memória RAM", f"{total_capacity} GB Total ({' + '.join(details)})")

    gpu_data = run_powershell("Get-CimInstance Win32_VideoController | Select-Object Name")
    if gpu_data:
        if not isinstance(gpu_data, list): gpu_data = [gpu_data]
        names = " + ".join([g.get('Name', '') for g in gpu_data if g.get('Name')])
        db.update_hardware_spec("Placa de Vídeo (GPU)", names)

    mobo_data = run_powershell("Get-CimInstance Win32_BaseBoard | Select-Object Product, Manufacturer")
    if mobo_data:
        if isinstance(mobo_data, list): mobo_data = mobo_data[0]
        full_name = f"{mobo_data.get('Manufacturer', '')} {mobo_data.get('Product', '')}"
        db.update_hardware_spec("Placa Mãe", full_name.strip())

    disk_data = run_powershell("Get-CimInstance Win32_LogicalDisk | Where-Object {$_.DriveType -eq 3} | Select-Object DeviceID, Size, FreeSpace")
    if disk_data:
        if not isinstance(disk_data, list): disk_data = [disk_data]
        disk_info = []
        for d in disk_data:
            letter = d.get('DeviceID', '?')
            total_gb = round(d.get('Size', 0) / (1024**3), 0)
            free_gb = round(d.get('FreeSpace', 0) / (1024**3), 0)
            disk_info.append(f"[{letter}] {total_gb}GB Total ({free_gb}GB Livre)")
        db.update_hardware_spec("Armazenamento", " | ".join(disk_info))

    log.info("✅ Hardware Scan Completo. Identidade do sistema atualizada.")
