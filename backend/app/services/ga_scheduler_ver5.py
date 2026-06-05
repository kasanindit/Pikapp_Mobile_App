from __future__ import annotations

import copy
import random
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Optional, Tuple

from models.ga_models_ver4 import (
    BSU,
    DailySchedule,
    FitnessDetail,
    GAResult,
    GenerationSnapshot,
    ScheduleConfig,
)
from services.ga_setup_ver4 import (
    build_daily_schedule,
    build_preflight_warnings,
    get_working_days,
)


@dataclass(frozen=True)
class ScheduleGene:
    bsu: BSU
    day: date

Chromosome = List[ScheduleGene]

def clone_chromosome(chromosome: Chromosome) -> Chromosome:
    return [
        ScheduleGene(bsu=gene.bsu, day=gene.day)
        for gene in chromosome
    ]

def normalize_kecamatan(value: str) -> str:
    return (value or "").strip().lower()

def validate_problem_feasibility(
    active_bsu: List[BSU],
    working_days: List[date],
    config: ScheduleConfig,
) -> None:
    total_bsu = len(active_bsu)
    total_days = len(working_days)
    total_slot = total_days * config.max_bsu_per_day

    if total_bsu == 0:
        raise ValueError("Tidak ada BSU aktif yang dapat dijadwalkan.")

    if total_days == 0:
        raise ValueError("Tidak ada hari kerja pada periode target.")

    if config.max_bsu_per_day not in (2, 3):
        raise ValueError("Maksimal BSU per hari harus bernilai 2 atau 3.")

    if total_bsu < total_days:
        raise ValueError(
            "Jumlah BSU aktif lebih sedikit dari jumlah hari kerja. "
            "Semua weekday tidak mungkin terisi minimal 1 BSU."
        )

    if total_bsu > total_slot:
        raise ValueError(
            "Jumlah BSU aktif melebihi kapasitas slot bulanan. "
            f"Jumlah BSU aktif: {total_bsu}, total slot: {total_slot}."
        )

def create_random_day_slots(
    total_bsu: int,
    working_days: List[date],
    max_bsu_per_day: int,
) -> List[date]:
    day_counts: Dict[date, int] = {day: 1 for day in working_days}
    remaining = total_bsu - len(working_days)

    while remaining > 0:
        candidate_days = [
            day for day in working_days
            if day_counts[day] < max_bsu_per_day
        ]

        selected_day = random.choice(candidate_days)
        day_counts[selected_day] += 1
        remaining -= 1

    slots: List[date] = []
    for day, count in day_counts.items():
        slots.extend([day] * count)

    random.shuffle(slots)
    return slots


def create_random_chromosome(
    active_bsu: List[BSU],
    working_days: List[date],
    config: ScheduleConfig,
) -> Chromosome:
    bsu_copy = copy.copy(active_bsu)
    random.shuffle(bsu_copy)

    day_slots = create_random_day_slots(
        total_bsu=len(active_bsu),
        working_days=working_days,
        max_bsu_per_day=config.max_bsu_per_day,
    )

    return [
        ScheduleGene(bsu=bsu, day=day)
        for bsu, day in zip(bsu_copy, day_slots)
    ]

def create_initial_population(
    active_bsu: List[BSU],
    working_days: List[date],
    config: ScheduleConfig,
) -> List[Chromosome]:
    population: List[Chromosome] = []

    for _ in range(config.population_size):
        chromosome = create_random_chromosome(
            active_bsu=active_bsu,
            working_days=working_days,
            config=config,
        )
        population.append(chromosome)

    return population

def build_schedule_from_chromosome(
    chromosome: Chromosome,
    working_days: List[date],
) -> List[DailySchedule]:
    assignment: Dict[date, List[BSU]] = {
        day: [] for day in working_days
    }

    for gene in chromosome:
        if gene.day in assignment:
            assignment[gene.day].append(gene.bsu)

    return [
        build_daily_schedule(day, assignment[day])
        for day in working_days
    ]


def calculate_schedule_integrity(
    schedule: List[DailySchedule],
    active_bsu: List[BSU],
) -> Tuple[int, int, int]:
    expected_ids = {bsu.bsu_id for bsu in active_bsu}

    scheduled_ids: List[str] = []
    for daily in schedule:
        scheduled_ids.extend(item.bsu_id for item in daily.items)

    scheduled_set = set(scheduled_ids)

    scheduled_bsu_count = len(scheduled_set)
    missing_bsu_count = len(expected_ids - scheduled_set)
    duplicate_bsu_count = len(scheduled_ids) - len(scheduled_set)

    return scheduled_bsu_count, missing_bsu_count, duplicate_bsu_count
    
    
def calculate_fitness(
    schedule: List[DailySchedule],
    active_bsu: List[BSU],
    working_days: List[date],
    config: ScheduleConfig,
) -> FitnessDetail:
    total_days = len(working_days)

    if total_days == 0:
        return FitnessDetail(
            coverage_penalty=1.0,
            capacity_penalty=1.0,
            max_bsu_penalty=1.0,
            kecamatan_penalty=1.0,
            total_penalty=100.0,
            fitness=1 / 101,
            total_distance=0.0,
            mixed_district_days=0,
            used_days=0,
            scheduled_bsu_count=0,
            missing_bsu_count=len(active_bsu),
            duplicate_bsu_count=0,
            empty_days_count=0,
            overloaded_days_count=0,
            over_quota_days_count=0,
        )

    empty_days_count = 0
    overloaded_days_count = 0
    over_quota_days_count = 0
    mixed_district_days = 0

    capacity_penalty = 0.0
    max_bsu_penalty = 0.0
    kecamatan_penalty = 0.0
    volume_balance_penalty = 0.0

    scheduled_ids: List[str] = []
    daily_volumes: List[float] = []

    min_bsu_per_day = getattr(config, "min_bsu_per_day", 1)

    for daily in schedule:
        bsu_count = len(daily.items)
        daily_volumes.append(daily.total_volume)

        if bsu_count < min_bsu_per_day:
            empty_days_count += 1

        if daily.total_volume > config.vehicle_capacity_kg:
            overloaded_days_count += 1
            excess_volume = daily.total_volume - config.vehicle_capacity_kg
            capacity_penalty += excess_volume / config.vehicle_capacity_kg

        if bsu_count > config.max_bsu_per_day:
            over_quota_days_count += 1
            excess_bsu = bsu_count - config.max_bsu_per_day
            max_bsu_penalty += excess_bsu / config.max_bsu_per_day

        if bsu_count > 1:
            kecamatan_counter = Counter(
                normalize_kecamatan(item.kecamatan)
                for item in daily.items
            )
            if len(kecamatan_counter) > 1:
                mixed_district_days += 1
                dominant_count = max(kecamatan_counter.values())
                minority_count = bsu_count - dominant_count
                kecamatan_penalty += minority_count / bsu_count

        scheduled_ids.extend(item.bsu_id for item in daily.items)

    scheduled_bsu_count, missing_bsu_count, duplicate_bsu_count = calculate_schedule_integrity(
        schedule=schedule,
        active_bsu=active_bsu,
    )

    total_volume = sum(daily_volumes)
    average_volume = total_volume / total_days if total_days > 0 else 0.0
    if average_volume > 0:
        volume_balance_penalty = sum(
            abs(volume - average_volume) / average_volume
            for volume in daily_volumes
        ) / total_days

    coverage_penalty = empty_days_count / total_days
    capacity_penalty = capacity_penalty / total_days
    max_bsu_penalty = max_bsu_penalty / total_days
    kecamatan_penalty = kecamatan_penalty / total_days

    total_penalty = (
        coverage_penalty * config.coverage_weight
        + max_bsu_penalty * config.max_bsu_weight
        + kecamatan_penalty * config.kecamatan_weight
        + capacity_penalty * config.capacity_weight
        + volume_balance_penalty * config.volume_balance_weight
    )
    fitness = 1 / (1 + total_penalty)

    return FitnessDetail(
        coverage_penalty=coverage_penalty,
        capacity_penalty=capacity_penalty,
        max_bsu_penalty=max_bsu_penalty,
        kecamatan_penalty=kecamatan_penalty,
        total_penalty=total_penalty,
        fitness=fitness,
        total_distance=sum(daily.total_distance for daily in schedule),
        mixed_district_days=mixed_district_days,
        used_days=total_days - empty_days_count,
        scheduled_bsu_count=scheduled_bsu_count,
        missing_bsu_count=missing_bsu_count,
        duplicate_bsu_count=duplicate_bsu_count,
        empty_days_count=empty_days_count,
        overloaded_days_count=overloaded_days_count,
        over_quota_days_count=over_quota_days_count,
    )

def tournament_selection(
    population: List[Chromosome],
    fitness_map: Dict[int, FitnessDetail],
    config: ScheduleConfig,
) -> Chromosome:
    tournament_size = min(config.tournament_size, len(population))
    selected_indices = random.sample(range(len(population)), tournament_size)
    best_index = max(selected_indices, key=lambda index: fitness_map[index].fitness)
    return clone_chromosome(population[best_index])


def uniform_crossover(
    parent1: Chromosome,
    parent2: Chromosome,
) -> Tuple[Chromosome, Chromosome]:
    p1_map = {gene.bsu.bsu_id: gene for gene in parent1}
    p2_map = {gene.bsu.bsu_id: gene for gene in parent2}

    child1: Chromosome = []
    child2: Chromosome = []

    bsu_ids = list(p1_map.keys())
    random.shuffle(bsu_ids)

    for bsu_id in bsu_ids:
        gene1 = p1_map[bsu_id]
        gene2 = p2_map[bsu_id]

        if random.random() < 0.5:
            child1.append(ScheduleGene(bsu=gene1.bsu, day=gene1.day))
            child2.append(ScheduleGene(bsu=gene2.bsu, day=gene2.day))
        else:
            child1.append(ScheduleGene(bsu=gene1.bsu, day=gene2.day))
            child2.append(ScheduleGene(bsu=gene2.bsu, day=gene1.day))

    return child1, child2

# def two_point_crossover(
#     parent1: Chromosome,
#     parent2: Chromosome,
# ) -> Tuple[Chromosome, Chromosome]:
#     p1_map = {gene.bsu.bsu_id: gene for gene in parent1}
#     p2_map = {gene.bsu.bsu_id: gene for gene in parent2}

#     bsu_ids = sorted(p1_map.keys())

#     if len(bsu_ids) < 3:
#         return one_point_day_crossover(parent1, parent2)

#     start, end = sorted(random.sample(range(len(bsu_ids)), 2))

#     child1: Chromosome = []
#     child2: Chromosome = []

#     for index, bsu_id in enumerate(bsu_ids):
#         gene1 = p1_map[bsu_id]
#         gene2 = p2_map[bsu_id]

#         if start <= index <= end:
#             child1.append(ScheduleGene(bsu=gene1.bsu, day=gene2.day))
#             child2.append(ScheduleGene(bsu=gene2.bsu, day=gene1.day))
#         else:
#             child1.append(ScheduleGene(bsu=gene1.bsu, day=gene1.day))
#             child2.append(ScheduleGene(bsu=gene2.bsu, day=gene2.day))

#     return child1, child2

# swap tanggal antara 2 bsu
def swap_mutation(
    chromosome: Chromosome,
    config: ScheduleConfig,
) -> Chromosome:
    mutated = clone_chromosome(chromosome)

    if random.random() < config.mutation_rate and len(mutated) >= 2:
        index1, index2 = random.sample(range(len(mutated)), 2)

        gene1 = mutated[index1]
        gene2 = mutated[index2]

        mutated[index1] = ScheduleGene(
            bsu=gene1.bsu,
            day=gene2.day,
        )

        mutated[index2] = ScheduleGene(
            bsu=gene2.bsu,
            day=gene1.day,
        )

    return mutated

# def mutate_chromosome(
#     chromosome: Chromosome,
#     working_days: List[date],
#     config: ScheduleConfig,
# ) -> Chromosome:
#     mutated = clone_chromosome(chromosome)

#     if not mutated:
#         return mutated

#     # Mutasi 1: pindahkan satu BSU ke tanggal lain.
#     # Ini membuat coverage/max/day distribution benar-benar dipengaruhi fitness.
#     if random.random() < config.mutation_rate:
#         index = random.randrange(len(mutated))
#         old_gene = mutated[index]
#         new_day = random.choice(working_days)
#         mutated[index] = ScheduleGene(bsu=old_gene.bsu, day=new_day)

#     # Mutasi 2: tukar tanggal antara dua BSU.
#     # Ini menjaga jumlah BSU per hari relatif stabil, tapi bisa memperbaiki kecamatan/volume.
#     if random.random() < config.mutation_rate and len(mutated) >= 2:
#         index1, index2 = random.sample(range(len(mutated)), 2)
#         gene1 = mutated[index1]
#         gene2 = mutated[index2]
#         mutated[index1] = ScheduleGene(bsu=gene1.bsu, day=gene2.day)
#         mutated[index2] = ScheduleGene(bsu=gene2.bsu, day=gene1.day)

#     return mutated


def should_record_generation(generation: int, total_generations: int) -> bool:
    generation_number = generation + 1
    return (
        generation_number == 1
        or generation_number % 10 == 0
        or generation_number == total_generations
    )


def build_generation_snapshot(generation: int, detail: FitnessDetail) -> GenerationSnapshot:
    return GenerationSnapshot(
        generation=generation + 1,
        best_fitness=detail.fitness,
        total_penalty=detail.total_penalty,
        capacity_penalty=detail.capacity_penalty,
        kecamatan_penalty=detail.kecamatan_penalty,
        max_bsu_penalty=detail.max_bsu_penalty,
        empty_days_count=detail.empty_days_count,
        overloaded_days_count=detail.overloaded_days_count,
        over_quota_days_count=detail.over_quota_days_count,
        mixed_district_days=detail.mixed_district_days,
    )


def generate_schedule_with_ga_v5(
    bsu_list: List[BSU],
    config: ScheduleConfig,
) -> GAResult:
    if config.random_seed is not None:
        random.seed(config.random_seed)

    active_bsu = [
        bsu for bsu in bsu_list
        if bsu.is_active
    ]

    working_days = get_working_days(
        config.start_date,
        config.end_date,
        use_indonesian_holidays=config.use_indonesian_holidays,
        additional_holidays=config.additional_holidays,
    )

    validate_problem_feasibility(
        active_bsu=active_bsu,
        working_days=working_days,
        config=config,
    )

    warnings = build_preflight_warnings(
        active_bsu_count=len(active_bsu),
        working_day_count=len(working_days),
        config=config,
    )

    population = create_initial_population(
        active_bsu=active_bsu,
        working_days=working_days,
        config=config,
    )

    best_chromosome: Optional[Chromosome] = None
    best_fitness_detail: Optional[FitnessDetail] = None
    generation_found = 0

    fitness_history: List[float] = []
    generation_snapshots: List[GenerationSnapshot] = []

    for generation in range(config.generations):
        fitness_map: Dict[int, FitnessDetail] = {}

        for index, chromosome in enumerate(population):
            schedule = build_schedule_from_chromosome(
                chromosome=chromosome,
                working_days=working_days,
            )

            fitness_map[index] = calculate_fitness(
                schedule=schedule,
                active_bsu=active_bsu,
                working_days=working_days,
                config=config,
            )

        current_best_index = max(
            fitness_map.keys(),
            key=lambda index: fitness_map[index].fitness,
        )

        current_best_fitness = fitness_map[current_best_index]
        fitness_history.append(current_best_fitness.fitness)

        if should_record_generation(generation, config.generations):
            generation_snapshots.append(
                build_generation_snapshot(generation, current_best_fitness)
            )

        if (
            best_fitness_detail is None
            or current_best_fitness.fitness > best_fitness_detail.fitness
        ):
            best_chromosome = clone_chromosome(
                population[current_best_index]
            )
            best_fitness_detail = current_best_fitness
            generation_found = generation

        sorted_indices = sorted(
            fitness_map.keys(),
            key=lambda index: fitness_map[index].fitness,
            reverse=True,
        )

        elite_count = min(
            config.elitism_count,
            config.population_size,
        )

        new_population: List[Chromosome] = [
            clone_chromosome(population[index])
            for index in sorted_indices[:elite_count]
        ]

        while len(new_population) < config.population_size:
            parent1 = tournament_selection(
                population=population,
                fitness_map=fitness_map,
                config=config,
            )

            parent2 = tournament_selection(
                population=population,
                fitness_map=fitness_map,
                config=config,
            )

            if random.random() < config.crossover_rate:
                child1, child2 = uniform_crossover(parent1, parent2)
            else:
                child1 = clone_chromosome(parent1)
                child2 = clone_chromosome(parent2)

            child1 = swap_mutation(child1, config)
            child2 = swap_mutation(child2, config)

            new_population.append(child1)

            if len(new_population) < config.population_size:
                new_population.append(child2)

        population = new_population

    if best_chromosome is None or best_fitness_detail is None:
        raise RuntimeError("Algoritma genetika gagal menghasilkan jadwal.")

    final_schedule = build_schedule_from_chromosome(
        chromosome=best_chromosome,
        working_days=working_days,
    )

    final_fitness_detail = calculate_fitness(
        schedule=final_schedule,
        active_bsu=active_bsu,
        working_days=working_days,
        config=config,
    )

    return GAResult(
        best_chromosome=[gene.bsu for gene in best_chromosome],
        best_schedule=final_schedule,
        best_fitness=final_fitness_detail.fitness,
        fitness_detail=final_fitness_detail,
        generation_found=generation_found,
        fitness_history=fitness_history,
        generation_snapshots=generation_snapshots,
        warnings=warnings,
        working_day_count=len(working_days),
        total_slot=len(working_days) * config.max_bsu_per_day,
        max_bsu_per_day=config.max_bsu_per_day,
        vehicle_capacity_kg=config.vehicle_capacity_kg,
    )
