import datetime as _dt
from extensions import db


class PC(db.Model):
    __tablename__ = "pcs"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False, index=True)
    location = db.Column(db.String(120), default="")
    # Spek standar kelengkapan
    ram_sticks = db.Column(db.Integer, nullable=False, default=1)
    ram_capacity_gb = db.Column(db.Integer, nullable=False, default=8)  # GB per keping
    ssd_count = db.Column(db.Integer, nullable=False, default=1)
    ssd_capacity_gb = db.Column(db.Integer, nullable=False, default=256)
    hdd_count = db.Column(db.Integer, nullable=False, default=0)       # 0 = tidak wajib HDD
    hdd_capacity_gb = db.Column(db.Integer, nullable=False, default=0)  # GB per HDD (mode seragam, kompat lama)
    hdd_capacities = db.Column(db.String(200), default="")  # kapasitas tiap HDD, CSV (mis. "500,1000") - utk HDD beda kapasitas
    gpu_name = db.Column(db.String(120), default="")  # optional
    monitor_count = db.Column(db.Integer, nullable=False, default=1)
    monitor_size_inch = db.Column(db.Integer, nullable=False, default=24)  # ukuran per monitor (inch)
    monitor_brand = db.Column(db.String(120), default="")  # merk monitor (opsional)
    notes = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=_dt.datetime.now)
    updated_at = db.Column(db.DateTime, default=_dt.datetime.now, onupdate=_dt.datetime.now)

    inspections = db.relationship(
        "Inspection", backref="pc", cascade="all, delete-orphan", order_by="Inspection.inspected_at.desc()"
    )

    def __repr__(self):
        return f"<PC {self.name}>"

    @property
    def latest_inspection(self):
        return self.inspections[0] if self.inspections else None

    @property
    def hdd_list(self):
        """Daftar kapasitas HDD standar (GB). Pakai hdd_capacities (CSV) bila ada,
        jika tidak fallback ke hdd_count x hdd_capacity_gb (mode seragam lama)."""
        raw = (self.hdd_capacities or "").strip()
        if raw:
            out = []
            for x in raw.split(","):
                x = x.strip()
                if x.isdigit():
                    out.append(int(x))
            if out:
                return out
        if self.hdd_count and self.hdd_capacity_gb:
            return [self.hdd_capacity_gb] * self.hdd_count
        return []

    @property
    def spec_text(self):
        parts = [
            f"RAM {self.ram_sticks}x{self.ram_capacity_gb}GB",
            f"SSD {self.ssd_count}x{self.ssd_capacity_gb}GB",
        ]
        hdds = self.hdd_list
        if hdds:
            if len(set(hdds)) == 1:
                parts.append(f"HDD {len(hdds)}x{hdds[0]}GB")
            else:
                parts.append("HDD " + "+".join(f"{c}GB" for c in hdds))
        if self.gpu_name:
            parts.append(f"GPU {self.gpu_name}")
        mon = f"Monitor {self.monitor_count}x{self.monitor_size_inch}\""
        if self.monitor_brand:
            mon += f" {self.monitor_brand}"
        parts.append(mon)
        return " | ".join(parts)


class Inspection(db.Model):
    __tablename__ = "inspections"
    id = db.Column(db.Integer, primary_key=True)
    pc_id = db.Column(db.Integer, db.ForeignKey("pcs.id"), nullable=False, index=True)
    inspected_at = db.Column(db.DateTime, default=_dt.datetime.now, index=True)
    status = db.Column(db.String(20), nullable=False, default="OK")  # OK / TIDAK_LENGKAP / OFFLINE
    note = db.Column(db.Text, default="")
    source = db.Column(db.String(20), default="web")  # web / telegram / api / agent / auto-weekly

    def __repr__(self):
        return f"<Inspection {self.pc_id} {self.status} {self.inspected_at}>"


class PCLive(db.Model):
    """Snapshot spek aktual terakhir dari agen di tiap PC (1 baris per PC, ditimpa tiap laporan)."""
    __tablename__ = "pc_live"
    id = db.Column(db.Integer, primary_key=True)
    pc_name = db.Column(db.String(120), unique=True, nullable=False, index=True)
    ip = db.Column(db.String(64), default="")
    hostname = db.Column(db.String(120), default="")
    last_seen = db.Column(db.DateTime, default=_dt.datetime.now, index=True)
    # Spek aktual hasil baca WMI, disimpan sebagai JSON string
    ram_json = db.Column(db.Text, default="")    # {"total_gb":16,"sticks":[{"size_gb":8},...]}
    disk_json = db.Column(db.Text, default="")   # [{"model":"...","size_gb":512,"media":"SSD"},...]
    gpu_json = db.Column(db.Text, default="")    # [{"name":"...","type":"..."}]
    agent_version = db.Column(db.String(40), default="")
    # Deteksi perubahan saat PC nyala ulang (boot-check)
    prev_fingerprint = db.Column(db.Text, default="")  # sidik jari spek sesi nyala sebelumnya
    was_online = db.Column(db.Boolean, default=False)  # status online terakhir yang diketahui
    last_compliance = db.Column(db.String(20), default="")  # kepatuhan vs standar terakhir: OK / TIDAK_LENGKAP
    last_boot_time = db.Column(db.String(40), default="")    # waktu boot Windows terakhir yang dilaporkan agen

    def __repr__(self):
        return f"<PCLive {self.pc_name} {self.last_seen}>"

    def is_online(self, max_age_seconds=180):
        if not self.last_seen:
            return False
        age = (_dt.datetime.now() - self.last_seen).total_seconds()
        return age <= max_age_seconds