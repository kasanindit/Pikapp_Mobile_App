from __future__ import annotations

import copy
import random
from typing import Dict, List, Optional, Tuple

from models.ga_models_ver4 import (
    BSU,
    DailySchedule,
    FitnessDetail,
    GAResult,
    GenerationSnapshot,
    ScheduleConfig,
)
from services.ga_setup_ver4 import build_daily_schedule, build_preflight_warnings, get_working_days


def create_initial_population(active_bsu: List[BSU], config: ScheduleConfig) -> List[List[BSU]]:
    population = []

    for _ in range(config.population_size):
        chromosome = copy.copy(active_bsu)
        random.shuffle(chromosome)
        population.append(chromosome)

    return population


# def decode_chromosome(
#     chromosome: List[BSU],
#     working_days: List,
#     config: ScheduleConfig,
# ) -> List[DailySchedule]:
#     assignment: Dict = {day: [] for day in working_days}

#     if not working_days:
#         return []

#     total_days = len(working_days)

#     for index, bsu in enumerate(chromosome[:total_days]):
#         assignment[working_days[index]].append(bsu)
    
#     for bsu in chromosome[total_days:]:
#         candidate_days = []

#         for day in working_days:
#             current_items = assignment[day]
#             current_volume = sum(item.estimated_volume_kg for item in current_items)
#             can_place_by_count = len(current_items) < config.max_bsu_per_day
#             # can_place_by_capacity = (
#             #     current_volume + bsu.estimated_volume_kg <= config.vehicle_capacity_kg
#             # )

#             if can_place_by_count :
#                 # same_kecamatan_score = 0 if bsu.kecamatan in {item.kecamatan for item in current_items} else 1
#                 volume_after_insert = current_volume + bsu.estimated_volume_kg
#                 count_after_insert = len(current_items) + 1
#                 candidate_days.append(
#                     (
#                         # same_kecamatan_score,
#                         count_after_insert,
#                         volume_after_insert,
#                         day,
#                     )
#                 )

#         if candidate_days:
#             # candidate_days.sort(key=lambda item: (item[0], item[1], item[2]))
#             # assignment[candidate_days[0][3]].append(bsu)
#             candidate_days.sort(key=lambda item: (item[0], item[1]))
#             assignment[candidate_days[0][2]].append(bsu)
#         else:
#             # Tetap masukkan BSU agar tidak hilang dari draft; pelanggaran dihitung oleh fitness.
#             lightest_day = min(
#                 working_days,
#                 key=lambda day: (
#                     len(assignment[day]),
#                     sum(item.estimated_volume_kg for item in assignment[day]),
#                 ),
#             )
#             assignment[lightest_day].append(bsu)

#     return [
#         build_daily_schedule(day, assignment[day])
#         for day in working_days
#     ]

def decode_chromosome(
    chromosome: List[BSU],
    working_days: List,
    config: ScheduleConfig,
) -> List[DailySchedule]:
    assignment: Dict = {day: [] for day in working_days}

    if not working_days:
        return []

    total_days = len(working_days)

    for index, bsu in enumerate(chromosome):
        day = working_days[index % total_days]
        assignment[day].append(bsu)

    return [
        build_daily_schedule(day, assignment[day])
        for day in working_days
    ]


def calculate_fitness(
    schedule: List[DailySchedule],
    chromosome: List[BSU],
    config: ScheduleConfig,
) -> FitnessDetail:
    total_days = len(schedule)

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
            missing_bsu_count=len(chromosome),
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
    scheduled_ids: List[str] = []

    for daily in schedule:
        bsu_count = len(daily.items)

        if bsu_count == 0:
            empty_days_count += 1

        if daily.total_volume > config.vehicle_capacity_kg:
            overloaded_days_count += 1
            excess_volume = daily.total_volume - config.vehicle_capacity_kg
            capacity_penalty += excess_volume / config.vehicle_capacity_kg

        if bsu_count > config.max_bsu_per_day:
            over_quota_days_count += 1
            excess_bsu = bsu_count - config.max_bsu_per_day
            max_bsu_penalty += excess_bsu / config.max_bsu_per_day

        unique_kecamatan_count = len(daily.kecamatan_list)
        if unique_kecamatan_count > 1:
            mixed_district_days += 1
            kecamatan_penalty += (unique_kecamatan_count - 1) / config.max_bsu_per_day

        scheduled_ids.extend(item.bsu_id for item in daily.items)

    scheduled_set = set(scheduled_ids)
    chromosome_set = {bsu.bsu_id for bsu in chromosome}
    missing_bsu_count = len(chromosome_set - scheduled_set)
    duplicate_bsu_count = len(scheduled_ids) - len(scheduled_set)

    coverage_penalty = empty_days_count / total_days
    capacity_penalty = capacity_penalty / total_days
    max_bsu_penalty = max_bsu_penalty / total_days
    kecamatan_penalty = kecamatan_penalty / total_days

    total_penalty = (
        coverage_penalty * config.coverage_weight
        + capacity_penalty * config.capacity_weight
        + max_bsu_penalty * config.max_bsu_weight
        + kecamatan_penalty * config.kecamatan_weight
        + missing_bsu_count * 10.0
        + duplicate_bsu_count * 10.0
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
        used_days=total_days,
        scheduled_bsu_count=len(scheduled_set),
        missing_bsu_count=missing_bsu_count,
        duplicate_bsu_count=duplicate_bsu_count,
        empty_days_count=empty_days_count,
        overloaded_days_count=overloaded_days_count,
        over_quota_days_count=over_quota_days_count,
    )


def tournament_selection(
    population: List[List[BSU]],
    fitness_map: Dict[int, FitnessDetail],
    config: ScheduleConfig,
) -> List[BSU]:
    tournament_size = min(config.tournament_size, len(population))
    selected_indices = random.sample(range(len(population)), tournament_size)
    best_index = max(selected_indices, key=lambda index: fitness_map[index].fitness)
    return copy.copy(population[best_index])


def order_crossover(parent1: List[BSU], parent2: List[BSU]) -> Tuple[List[BSU], List[BSU]]:
    size = len(parent1)

    if size < 2:
        return copy.copy(parent1), copy.copy(parent2)

    start, end = sorted(random.sample(range(size), 2))

    def make_child(p1: List[BSU], p2: List[BSU]) -> List[BSU]:
        child: List[Optional[BSU]] = [None] * size
        child[start:end + 1] = p1[start:end + 1]
        child_uids = {bsu.bsu_id for bsu in child if bsu is not None}
        p2_genes = [bsu for bsu in p2 if bsu.bsu_id not in child_uids]
        p2_index = 0

        for index in range(size):
            if child[index] is None:
                child[index] = p2_genes[p2_index]
                p2_index += 1

        return [bsu for bsu in child if bsu is not None]

    return make_child(parent1, parent2), make_child(parent2, parent1)


def swap_mutation(chromosome: List[BSU], mutation_rate: float) -> List[BSU]:
    mutated = copy.copy(chromosome)

    if random.random() < mutation_rate and len(mutated) >= 2:
        index1, index2 = random.sample(range(len(mutated)), 2)
        mutated[index1], mutated[index2] = mutated[index2], mutated[index1]

    return mutated


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


def generate_schedule_with_ga_v4(
    bsu_list: List[BSU],
    config: ScheduleConfig,
) -> GAResult:
    if config.random_seed is not None:
        random.seed(config.random_seed)

    active_bsu = [bsu for bsu in bsu_list if bsu.is_active]

    if not active_bsu:
        raise ValueError("Tidak ada BSU aktif yang dapat dijadwalkan.")

    working_days = get_working_days(
        config.start_date,
        config.end_date,
        use_indonesian_holidays=config.use_indonesian_holidays,
        additional_holidays=config.additional_holidays,
    )

    if not working_days:
        raise ValueError("Tidak ada hari kerja pada periode target.")

    warnings = build_preflight_warnings(
        active_bsu_count=len(active_bsu),
        working_day_count=len(working_days),
        config=config,
    )

    population = create_initial_population(active_bsu, config)
    best_chromosome: Optional[List[BSU]] = None
    best_fitness_detail: Optional[FitnessDetail] = None
    generation_found = 0
    fitness_history: List[float] = []
    generation_snapshots: List[GenerationSnapshot] = []

    for generation in range(config.generations):
        fitness_map: Dict[int, FitnessDetail] = {}

        for index, chromosome in enumerate(population):
            schedule = decode_chromosome(chromosome, working_days, config)
            fitness_map[index] = calculate_fitness(schedule, chromosome, config)

        current_best_index = max(
            fitness_map.keys(),
            key=lambda index: fitness_map[index].fitness,
        )
        current_best_fitness = fitness_map[current_best_index]
        fitness_history.append(current_best_fitness.fitness)
        if should_record_generation(generation, config.generations):
            generation_snapshots.append(build_generation_snapshot(generation, current_best_fitness))

        if (
            best_fitness_detail is None
            or current_best_fitness.fitness > best_fitness_detail.fitness
        ):
            best_chromosome = copy.copy(population[current_best_index])
            best_fitness_detail = current_best_fitness
            generation_found = generation

        sorted_indices = sorted(
            fitness_map.keys(),
            key=lambda index: fitness_map[index].fitness,
            reverse=True,
        )

        elite_count = min(config.elitism_count, config.population_size)
        new_population = [
            copy.copy(population[index])
            for index in sorted_indices[:elite_count]
        ]

        while len(new_population) < config.population_size:
            parent1 = tournament_selection(population, fitness_map, config)
            parent2 = tournament_selection(population, fitness_map, config)

            if random.random() < config.crossover_rate:
                child1, child2 = order_crossover(parent1, parent2)
            else:
                child1, child2 = copy.copy(parent1), copy.copy(parent2)

            new_population.append(swap_mutation(child1, config.mutation_rate))
            if len(new_population) < config.population_size:
                new_population.append(swap_mutation(child2, config.mutation_rate))

        population = new_population

    if best_chromosome is None or best_fitness_detail is None:
        raise RuntimeError("Algoritma genetika gagal menghasilkan jadwal.")

    final_schedule = decode_chromosome(best_chromosome, working_days, config)
    final_fitness_detail = calculate_fitness(final_schedule, best_chromosome, config)

    return GAResult(
        best_chromosome=best_chromosome,
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
