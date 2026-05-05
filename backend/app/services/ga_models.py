import math, random, copy
from dataclasses import dataclass, field
from datetime import date, timedelta
from itertools import permutations
from typing import Optional

@dataclass
class BSU:
    bsu_id: str
    nama: str
    kecamatan: str
    lat: float
    lon: float
    estimasi_vol_kg: float
    is_aktif: bool = True
 
@dataclass
class Slot:
    bsu_id: str
    nama: str
    kecamatan: str
    vol_kg: float
    lat: float
    lon: float
    req_terpenuhi: bool = False
 
@dataclass
class HariJadwal:
    tanggal: date
    slots: list[Slot] = field(default_factory=list)
 
    @property
    def total_vol(self): return sum(s.vol_kg for s in self.slots)

Chromosome = list[HariJadwal]

# Formula Haversine
def haversine(lat1, lon1, lat2, lon2) -> float:
    R = 6371.0
    dlat, dlon = math.radians(lat2-lat1), math.radians(lon2-lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    # Proteksi math domain error
    return 2 * R * math.asin(math.sqrt(max(0.0, min(1.0, a))))

def std_dev(values: list[float]) -> float:
    if len(values) < 2: return 0.0
    mean = sum(values) / len(values)
    return math.sqrt(sum((v - mean)**2 for v in values) / len(values))

def hari_operasional(tahun: int, bulan: int) -> list[date]:
    # Ganti set ini dengan library holidays di produksi
    libur = {date(2025,1,1), date(2025,3,29), date(2025,3,31), date(2025,4,1),
             date(2025,5,1), date(2025,5,29), date(2025,6,1), date(2025,8,17), date(2025,12,25)}
    result, d = [], date(tahun, bulan, 1)
    while d.month == bulan:
        if d.weekday() < 5 and d not in libur:
            result.append(d)
        d += timedelta(days=1)
    return result

# Fitness
def fitness(c: Chromosome, requests: dict, kapasitas=1000.0, min_bsu=1, max_bsu=3, w1=0.30, w2=0.25, w3=0.45) -> float:
    if not c: return 0.0001

    penalty = 0.0
    seen = set()
    
    for h in c:
        # Penalti jika melebihi atau kurang dari kuota harian
        if len(h.slots) > max_bsu:
            penalty += (len(h.slots) - max_bsu) * 2.0
        if len(h.slots) < min_bsu:
            penalty += (min_bsu - len(h.slots)) * 1.0

        # Penalti jika melebihi kapasitas truk
        if h.total_vol > kapasitas:
            penalty += (h.total_vol - kapasitas) / kapasitas * 5.0

        # Penalti jika BSU duplikat (sangat berat)
        for s in h.slots:
            if s.bsu_id in seen:
                penalty += 10.0
            seen.add(s.bsu_id)

    # Soft constraint (hanya dihitung jika penalti rendah)
    jarak_list = [
        sum(haversine(h.slots[i].lat, h.slots[i].lon, h.slots[i+1].lat, h.slots[i+1].lon)
            for i in range(len(h.slots)-1)) / max(len(h.slots)-1, 1)
        for h in c
    ]
    f_jarak = max(0.0, 1.0 - (sum(jarak_list)/len(jarak_list)) / 15.0) if jarak_list else 0.0

    vols = [h.total_vol for h in c]
    mean_v = sum(vols)/len(vols) if vols else 0.0
    f_beban = max(0.0, 1.0 - std_dev(vols) / mean_v) if mean_v > 0 else 0.0

    terpenuhi = sum(1 for h in c for s in h.slots if s.req_terpenuhi)
    f_request = terpenuhi / max(len(requests), 1)

    # Jika ada penalti, nilai fitness akan sangat kecil tapi tidak 0
    # Ini agar GA tetap bisa melakukan seleksi (pilih yang penaltinya paling kecil)
    if penalty > 0:
        return 0.1 / (1.0 + penalty)

    return round(w1*f_jarak + w2*f_beban + w3*f_request, 6)

def buat_kromosom(hari_ops: list[date], bsu_list: list[BSU],
                  requests: dict, kapasitas: float, min_bsu: int, max_bsu: int) -> Chromosome:
    assignment: dict[date, list[BSU]] = {d: [] for d in hari_ops}
    pool = bsu_list.copy()
    random.shuffle(pool)
 
    def bisa_masuk(bsu, hari):
        cur = assignment[hari]
        return len(cur) < max_bsu and sum(b.estimasi_vol_kg for b in cur) + bsu.estimasi_vol_kg <= kapasitas
 
    sisa = []
    for bsu in pool:
        if bsu.bsu_id in requests and requests[bsu.bsu_id] in assignment:
            if bisa_masuk(bsu, requests[bsu.bsu_id]):
                assignment[requests[bsu.bsu_id]].append(bsu)
                continue
        sisa.append(bsu)
 
    # Distribusikan sisa BSU secara lebih agresif
    for bsu in sisa:
        kandidat = [d for d in hari_ops if bisa_masuk(bsu, d)]
        if kandidat:
            assignment[random.choice(kandidat)].append(bsu)
        else:
            # Jika tidak muat di mana pun, paksa masuk ke hari yang paling kosong
            # agar BSU tidak hilang dari jadwal
            target = min(hari_ops, key=lambda d: len(assignment[d]))
            assignment[target].append(bsu)
 
    # Bangun kromosom (semua hari yang punya BSU dimasukkan)
    kromosom = []
    for tanggal in sorted(hari_ops):
        bsu_hari = assignment[tanggal]
        if bsu_hari:
            kromosom.append(HariJadwal(
                tanggal=tanggal,
                slots=[Slot(b.bsu_id, b.nama, b.kecamatan, b.estimasi_vol_kg,
                            b.lat, b.lon,
                            req_terpenuhi=b.bsu_id in requests and requests[b.bsu_id] == tanggal)
                       for b in bsu_hari]
            ))
    return kromosom

# tournament selection
def seleksi(populasi, fit_fn, k=5):
    return max(random.sample(populasi, min(k, len(populasi))), key=fit_fn)

# OX Crossover
def crossover(p1: Chromosome, p2: Chromosome, kapasitas: float, min_bsu: int, max_bsu: int) -> Chromosome:
    if not p1 or not p2: return copy.deepcopy(p1 or p2)
    n = len(p1)
    if n < 2: return copy.deepcopy(p1)
    
    i, j = sorted(random.sample(range(n), 2))
    slice_p1 = p1[i:j+1]
    child_map = {h.tanggal: h for h in slice_p1}
    
    ada_bsu = {s.bsu_id for h in slice_p1 for s in h.slots}
    sisa_bsu = [s for h in p2 for s in h.slots if s.bsu_id not in ada_bsu]
    
    # Ambil hari-hari lain dari p1 yang tidak masuk slice
    hari_lain = [h.tanggal for idx, h in enumerate(p1) if not (i <= idx <= j)]
    
    ptr = 0
    for tgl in hari_lain:
        slots_baru, vol = [], 0.0
        # Coba isi hari ini dengan sisa BSU dari p2
        while ptr < len(sisa_bsu) and len(slots_baru) < max_bsu:
            s = sisa_bsu[ptr]
            if vol + s.vol_kg <= kapasitas:
                slots_baru.append(copy.deepcopy(s))
                vol += s.vol_kg
                ptr += 1
            else:
                break
        
        if slots_baru:
            child_map[tgl] = HariJadwal(tanggal=tgl, slots=slots_baru)
    
    # Jika masih ada sisa BSU yang belum terjadwalkan, masukkan paksa ke hari yang ada
    while ptr < len(sisa_bsu):
        target_tgl = min(child_map.keys(), key=lambda t: len(child_map[t].slots))
        child_map[target_tgl].slots.append(copy.deepcopy(sisa_bsu[ptr]))
        ptr += 1

    return sorted(child_map.values(), key=lambda h: h.tanggal)

# Swap Mutation
def mutasi(c: Chromosome, kapasitas: float, pm=0.12) -> Chromosome:
    if random.random() > pm or len(c) < 2: return c
    r = copy.deepcopy(c)
    i, j = random.sample(range(len(r)), 2)
    if not r[i].slots or not r[j].slots: return r
    si, sj = random.randrange(len(r[i].slots)), random.randrange(len(r[j].slots))
    vi = r[i].total_vol - r[i].slots[si].vol_kg + r[j].slots[sj].vol_kg
    vj = r[j].total_vol - r[j].slots[sj].vol_kg + r[i].slots[si].vol_kg
    if vi <= kapasitas and vj <= kapasitas:
        r[i].slots[si], r[j].slots[sj] = r[j].slots[sj], r[i].slots[si]
    return r
 
def repair(c: Chromosome, bsu_list: list[BSU], kapasitas: float, max_bsu: int) -> Chromosome:
    r = copy.deepcopy(c)
    ada = {s.bsu_id for h in r for s in h.slots}
    for bsu in bsu_list:
        if bsu.bsu_id in ada: continue
        for h in sorted(r, key=lambda h: (len(h.slots), h.total_vol)):
            if len(h.slots) < max_bsu and h.total_vol + bsu.estimasi_vol_kg <= kapasitas:
                h.slots.append(Slot(bsu.bsu_id, bsu.nama, bsu.kecamatan,
                                    bsu.estimasi_vol_kg, bsu.lat, bsu.lon))
                break
    return r
 
def optimasi_urutan(c: Chromosome) -> Chromosome:
    r = copy.deepcopy(c)
    for h in r:
        if len(h.slots) > 1:
            h.slots = list(min(permutations(h.slots),
                               key=lambda p: sum(haversine(p[i].lat, p[i].lon, p[i+1].lat, p[i+1].lon)
                                                 for i in range(len(p)-1))))
    return r

# algortima Genetika
def jalankan_ga(tahun, bulan, bsu_list, requests,
                kapasitas=1000.0, min_bsu=1, max_bsu=3,
                pop_size=80, max_gen=250, pc=0.85, pm=0.12,
                w1=0.30, w2=0.25, w3=0.45) -> tuple[Chromosome, list[float]]:
 
    hari_ops = hari_operasional(tahun, bulan)
    fit_fn   = lambda c: fitness(c, requests, kapasitas, min_bsu, max_bsu, w1, w2, w3)
 
    pop = [buat_kromosom(hari_ops, bsu_list, requests, kapasitas, min_bsu, max_bsu)
           for _ in range(pop_size)]
    fit = [fit_fn(c) for c in pop]
 
    best_c = copy.deepcopy(pop[fit.index(max(fit))])
    best_f = max(fit)
    history, stagnasi, n_elite = [best_f], 0, max(1, pop_size // 20)
 
    for gen in range(1, max_gen + 1):
        terurut  = sorted(zip(fit, pop), key=lambda x: x[0], reverse=True)
        new_pop  = [copy.deepcopy(c) for _, c in terurut[:n_elite]]
 
        while len(new_pop) < pop_size:
            p1, p2 = seleksi(pop, fit_fn), seleksi(pop, fit_fn)
            anak   = crossover(p1, p2, kapasitas, min_bsu, max_bsu) if random.random() < pc else copy.deepcopy(p1)
            anak   = mutasi(anak, kapasitas, pm)
            anak   = repair(anak, bsu_list, kapasitas, max_bsu)
            new_pop.append(anak)
 
        pop, fit = new_pop, [fit_fn(c) for c in new_pop]
        gen_best = max(fit)
 
        if gen_best > best_f:
            best_f, best_c, stagnasi = gen_best, copy.deepcopy(pop[fit.index(gen_best)]), 0
        else:
            stagnasi += 1
 
        history.append(best_f)
        print(f"Gen {gen:4d} | best: {best_f:.4f} | stagnasi: {stagnasi}")
 
        if stagnasi >= 50: break
 
    return optimasi_urutan(best_c), history

def format_jadwal(jadwal: Chromosome) -> list[dict]:
    result = []
    for h in jadwal:
        hari_dict = {
            "tanggal": h.tanggal.isoformat(),
            "total_vol": h.total_vol,
            "slots": []
        }
        for s in h.slots:
            hari_dict["slots"].append({
                "bsu_id": s.bsu_id,
                "nama": s.nama,
                "kecamatan": s.kecamatan,
                "vol_kg": s.vol_kg,
                "lat": s.lat,
                "lon": s.lon,
                "req_terpenuhi": s.req_terpenuhi
            })
        result.append(hari_dict)
    return result

