from __future__ import annotations

import random
import math
from dataclasses import dataclass
from datetime import date, timedelta
from typing import List, Optional
from models.ga_models import *
from services.ga_setup import *

# inisialisasi populasi
def create_initial_population(
    bsu_list: List[BSU],
    population_size: int
) -> List[List[BSU]]:
    population = []

    for _ in range(population_size):
        chromosome = bsu_list[:]
        random.shuffle(chromosome)
        population.append(chromosome)

    return population

#fitness function
def calculate_fitness(
    chromosome: List[BSU],
    config: ScheduleConfig,
    max_distance: float,
    working_days: Optional[List[date]] = None
) -> float:
    return calculate_fitness_detail(
        chromosome=chromosome,
        config=config,
        max_distance=max_distance,
        working_days=working_days
    ).fitness

# tournament selection
def tournament_selection(
    population: List[List[BSU]],
    fitness_scores: List[float],
    tournament_size: int = 3
) -> List[BSU]:

    if not population:
        raise ValueError("Population tidak boleh kosong.")

    if len(population) < tournament_size:
        tournament_size = len(population)

    candidate_indexes = random.sample(range(len(population)), tournament_size)

    best_index = min(
        candidate_indexes,
        key=lambda index: fitness_scores[index]
    )

    return population[best_index][:]

# OX Crossover
def order_crossover(
    parent1: List[BSU],
    parent2: List[BSU]
) -> List[BSU]:
    size = len(parent1)

    if size < 2:
        return parent1[:]

    start, end = sorted(random.sample(range(size), 2))

    child: List[Optional[BSU]] = [None] * size

    child[start:end + 1] = parent1[start:end + 1]

    parent2_remaining = [
        bsu for bsu in parent2
        if bsu not in child
    ]

    index = 0

    for i in range(size):
        if child[i] is None:
            child[i] = parent2_remaining[index]
            index += 1

    return [
        bsu for bsu in child
        if bsu is not None
    ]

# mutasi
def swap_mutation(
    chromosome: List[BSU],
    mutation_rate: float
) -> List[BSU]:
    mutated = chromosome[:]

    if len(mutated) < 2:
        return mutated

    if random.random() < mutation_rate:
        index1, index2 = random.sample(range(len(mutated)), 2)
        mutated[index1], mutated[index2] = mutated[index2], mutated[index1]

    return mutated

def generate_schedule_with_ga(
    bsu_list: List[BSU],
    config: ScheduleConfig,
    population_size: int = 50,
    generations: int = 100,
    crossover_rate: float = 0.8,
    mutation_rate: float = 0.05,
    elitism_count: int = 2,
    random_seed: Optional[int] = None,
    verbose: bool = False,
    progress_interval: int = 10
) -> GAResult:
    if random_seed is not None:
        random.seed(random_seed)

    active_bsu = [
        bsu for bsu in bsu_list
        if bsu.is_active
    ]

    if not active_bsu:
        raise ValueError("Tidak ada BSU aktif yang dapat dijadwalkan.")

    total_weight = (
        config.weight_distance
        + config.weight_district
        + config.weight_volume
    )

    if round(total_weight, 5) != 1.0:
        raise ValueError("Total bobot fitness harus sama dengan 1.")

    working_days = get_working_days(
        config.start_date,
        config.end_date,
        use_indonesian_holidays=config.use_indonesian_holidays,
        additional_holidays=config.additional_holidays
    )

    # validate_problem_feasibility(
    #     active_bsu=active_bsu,
    #     working_days=working_days,
    #     config=config
    # )

    population = create_initial_population(
        active_bsu,
        population_size
    )

    max_distance = estimate_max_distance(
        population,
        config,
        working_days
    )

    best_chromosome: Optional[List[BSU]] = None
    best_fitness = float("inf")
    generation_found = 0
    fitness_history: List[float] = []

    for generation in range(generations):
        fitness_scores = [
            calculate_fitness(
                chromosome,
                config,
                max_distance,
                working_days
            )
            for chromosome in population
        ]

        sorted_indexes = sorted(
            range(len(population)),
            key=lambda index: fitness_scores[index]
        )

        population = [
            population[index]
            for index in sorted_indexes
        ]

        fitness_scores = [
            fitness_scores[index]
            for index in sorted_indexes
        ]

        current_best = population[0]

        current_best_detail = calculate_fitness_detail(
            chromosome=current_best,
            config=config,
            max_distance=max_distance,
            working_days=working_days
        )

        current_best_fitness = current_best_detail.fitness
        fitness_history.append(current_best_fitness)

        if current_best_fitness < best_fitness:
            best_fitness = current_best_fitness
            best_chromosome = current_best[:]
            generation_found = generation

        if verbose and (
            generation == 0
            or (generation + 1) % progress_interval == 0
            or generation == generations - 1
        ):
            print(
                f"Generasi {generation + 1}/{generations} | "
                f"best fitness: {best_fitness:.4f} | "
                f"current: {current_best_fitness:.4f}"
            )

        # Elitism
        new_population = [
            chromosome[:]
            for chromosome in population[:elitism_count]
        ]

        while len(new_population) < population_size:
            parent1 = tournament_selection(
                population,
                fitness_scores
            )

            parent2 = tournament_selection(
                population,
                fitness_scores
            )

            if random.random() < crossover_rate:
                child = order_crossover(parent1, parent2)
            else:
                child = parent1[:]

            child = swap_mutation(child, mutation_rate)

            new_population.append(child)

        population = new_population

    if best_chromosome is None:
        raise RuntimeError("GA gagal menghasilkan solusi.")

    best_schedule = decode_chromosome(
        chromosome=best_chromosome,
        config=config,
        working_days=working_days
    )

    best_detail = calculate_fitness_detail(
        chromosome=best_chromosome,
        config=config,
        max_distance=max_distance,
        working_days=working_days
    )

    return GAResult(
        best_chromosome=best_chromosome,
        best_schedule=best_schedule,
        best_fitness=best_fitness,
        fitness_detail=best_detail,
        generation_found=generation_found,
        fitness_history=fitness_history,
    )
