"""Initial knowledge base with scientific training knowledge.

Contains curated content from sports science literature.
Run this script to seed the knowledge base.
"""

from arete.rag.knowledge_base import Document, KnowledgeBase


def get_scientific_documents() -> list[Document]:
    """Scientific literature on training load and injury prevention."""
    return [
        Document(
            id="sci_gabbett_2016",
            content="""L'ACWR (Acute:Chronic Workload Ratio) est un indicateur clé du risque de blessure.
            Une étude sur 2000+ athlètes montre qu'un ACWR > 1.5 augmente le risque de blessure de 2 à 4 fois.
            La zone optimale se situe entre 0.8 et 1.3, appelée "sweet spot".
            La méthode EWMA (Exponentially Weighted Moving Average) est plus précise que la moyenne glissante classique.
            Recommandation : augmenter la charge de maximum 10% par semaine pour rester dans la zone optimale.""",
            metadata={
                "title": "The training-injury prevention paradox",
                "authors": ["Gabbett, T.J."],
                "year": 2016,
                "journal": "British Journal of Sports Medicine",
                "evidence_level": "high",
                "sports": ["all", "team_sports", "endurance"],
                "key_findings": [
                    "ACWR > 1.5 = risque blessure x2-4",
                    "Zone optimale: 0.8-1.3",
                    "EWMA plus précis que rolling average",
                    "Progression max 10%/semaine",
                ],
            },
        ),
        Document(
            id="sci_banister_1975",
            content="""Le modèle Fitness-Fatigue (Banister) modélise la performance comme:
            Performance = Fitness - Fatigue
            CTL (Chronic Training Load) représente la fitness, calculée sur 42 jours (EWMA).
            ATL (Acute Training Load) représente la fatigue, calculée sur 7 jours (EWMA).
            TSB (Training Stress Balance) = CTL - ATL représente la "forme" ou disponibilité.
            TSB positif (+5 à +25) : athlète frais, prêt pour performance ou intensité.
            TSB négatif (-10 à -30) : fatigue accumulée, risque de surentraînement.
            TSB très négatif (< -30) : surentraînement probable, repos obligatoire.""",
            metadata={
                "title": "A systems model of training for athletic performance",
                "authors": ["Banister, E.W.", "Calvert, T.W."],
                "year": 1975,
                "journal": "Australian Journal of Sports Medicine",
                "evidence_level": "high",
                "sports": ["all", "endurance"],
                "key_findings": [
                    "Performance = Fitness - Fatigue",
                    "CTL: fitness long terme (42j)",
                    "ATL: fatigue court terme (7j)",
                    "TSB positif = prêt pour performance",
                ],
            },
        ),
        Document(
            id="sci_foster_1998",
            content="""La monotonie d'entraînement est calculée comme:
            Monotonie = Charge moyenne / Écart-type de la charge
            Une monotonie > 2.0 indique un entraînement trop répétitif, augmentant le risque de:
            - Surentraînement
            - Blessures de surcharge
            - Stagnation de performance
            Le Strain (charge cumulée) = Charge totale × Monotonie
            Un Strain élevé (> 4000-6000 selon le sport) nécessite une période de récupération.
            Recommandation : varier les intensités, inclure des jours légers, alterner les types de séances.""",
            metadata={
                "title": "Monitoring training in athletes with reference to overtraining syndrome",
                "authors": ["Foster, C."],
                "year": 1998,
                "journal": "Medicine & Science in Sports & Exercise",
                "evidence_level": "high",
                "sports": ["all"],
                "key_findings": [
                    "Monotonie > 2.0 = risque surentraînement",
                    "Strain = Charge × Monotonie",
                    "Varier les intensités réduit le risque",
                ],
            },
        ),
        Document(
            id="sci_mujika_2004",
            content="""L'affûtage (tapering) avant compétition optimise la performance.
            Principes clés:
            - Réduction du volume de 40-60% sur 1-3 semaines
            - Maintien de l'intensité (95-100% de l'intensité normale)
            - Maintien de la fréquence d'entraînement
            Le tapering exponentiel est plus efficace que le tapering linéaire.
            Gains de performance attendus: 2-6% selon le sport.
            Attention: un tapering trop long (> 4 semaines) peut mener à du désentraînement.""",
            metadata={
                "title": "Scientific bases for precompetition tapering strategies",
                "authors": ["Mujika, I.", "Padilla, S."],
                "year": 2004,
                "journal": "Medicine & Science in Sports & Exercise",
                "evidence_level": "high",
                "sports": ["endurance", "swimming", "running"],
                "key_findings": [
                    "Réduire volume 40-60%",
                    "Maintenir intensité 95-100%",
                    "Tapering exponentiel optimal",
                    "Gains: 2-6%",
                ],
            },
        ),
        Document(
            id="sci_trimp_1991",
            content="""Le TRIMP (Training Impulse) quantifie la charge d'entraînement cardio:
            TRIMP = Durée × ΔFC × facteur_sexe
            où ΔFC = (FC_moy - FC_repos) / (FC_max - FC_repos)
            Facteur homme: 0.64 × e^(1.92 × ΔFC)
            Facteur femme: 0.86 × e^(1.67 × ΔFC)
            Le TRIMP permet de comparer des séances de différentes durées et intensités.
            TRIMP quotidien typique: 50-150 pour entraînement modéré, 150-300 pour intense.
            Cumul hebdomadaire: 400-800 pour amateur, 800-1500 pour élite.""",
            metadata={
                "title": "The TRIMP method for quantifying training load",
                "authors": ["Banister, E.W."],
                "year": 1991,
                "journal": "Canadian Journal of Sport Sciences",
                "evidence_level": "high",
                "sports": ["endurance", "cardio"],
                "key_findings": [
                    "TRIMP = Durée × ΔFC × facteur",
                    "Permet comparaison entre séances",
                    "50-150/jour modéré, 150-300 intense",
                ],
            },
        ),
    ]


def get_protocol_documents() -> list[Document]:
    """Training protocols and periodization schemes."""
    return [
        Document(
            id="proto_deload_week",
            content="""Protocole de semaine de décharge (deload):
            Objectif: Réduire fatigue accumulée, permettre surcompensation.
            Indications:
            - ACWR > 1.3 depuis 2+ semaines
            - TSB < -20
            - Monotonie > 2.0 prolongée
            - Fatigue subjective > 7/10
            
            Implémentation:
            - Réduire le volume de 40-50%
            - Réduire l'intensité de 20-30%
            - Maintenir la fréquence (éviter le repos complet)
            - Durée: 5-7 jours
            
            Exemple running:
            - Semaine normale: 50km avec 2 séances qualité
            - Semaine deload: 25-30km en endurance fondamentale uniquement
            
            ACWR cible après deload: retour vers 0.8-1.0""",
            metadata={
                "type": "protocol",
                "name": "Semaine de décharge",
                "sports": ["all", "endurance", "running"],
                "levels": ["intermediate", "advanced"],
                "trigger_conditions": ["acwr_high", "tsb_low", "high_fatigue"],
            },
        ),
        Document(
            id="proto_build_phase",
            content="""Phase de construction (Build Phase) en périodisation:
            Objectif: Augmenter progressivement la charge pour développer la fitness.
            
            Durée typique: 3-4 semaines de montée + 1 semaine deload
            
            Progression recommandée:
            - Semaine 1: 100% (baseline)
            - Semaine 2: 105-110%
            - Semaine 3: 110-120%
            - Semaine 4: 115-125%
            - Semaine 5: DELOAD (60-70%)
            
            ACWR cible: 1.0-1.2 (zone optimale haute)
            Monotonie cible: < 1.8
            
            Surveillance:
            - Si ACWR > 1.3: réduire la progression
            - Si TSB < -25: insérer récupération
            - Si fatigue > 7/10: jour off ou très léger""",
            metadata={
                "type": "protocol",
                "name": "Phase de construction",
                "sports": ["all", "endurance"],
                "levels": ["intermediate", "advanced"],
                "duration_weeks": 5,
                "acwr_target": [1.0, 1.2],
            },
        ),
        Document(
            id="proto_recovery_session",
            content="""Séance de récupération active:
            Objectif: Favoriser récupération sans accumulation de fatigue.
            
            Indications:
            - Jour après séance intense
            - TSB très négatif (< -15)
            - Fatigue ressentie > 6/10
            - ACWR élevé nécessitant réduction
            
            Structure type (45-60 min):
            - Échauffement: 10-15' très progressif
            - Corps: 25-35' en Z1 (< 65% FCM)
            - Retour au calme: 10-15' avec étirements
            
            Intensité: RPE 2-3/10, conversation aisée
            Éviter: toute accélération, dénivelé, terrain difficile
            
            Alternative: 30-40' vélo / natation / marche
            Contribution ACWR: minimale (charge très faible)""",
            metadata={
                "type": "protocol",
                "name": "Récupération active",
                "sports": ["all", "running", "endurance"],
                "levels": ["all"],
                "duration_min": 45,
            },
        ),
        Document(
            id="proto_interval_training",
            content="""Entraînement par intervalles (fractionné):
            Objectif: Développer VO2max et vitesse maximale aérobie.
            
            Types principaux:
            1. Courts (30/30, 200m): développement VO2max
               - 10-12 × 30" rapide / 30" récup
               - Allure: 100-110% VMA
               - Charge ACWR: modérée-haute
            
            2. Moyens (400-800m): seuil anaérobie
               - 6-8 × 400m récup 1'30
               - Allure: 95-100% VMA
               - Charge ACWR: haute
            
            3. Longs (1000-2000m): endurance spécifique
               - 4-5 × 1000m récup 2-3'
               - Allure: 90-95% VMA
               - Charge ACWR: très haute
            
            Fréquence: 1-2×/semaine selon niveau
            Prérequis: base aérobie solide (6-8 semaines endurance)
            
            Précautions si ACWR > 1.2:
            - Réduire nombre de répétitions
            - Augmenter temps de récupération
            - Remplacer par fartlek plus léger""",
            metadata={
                "type": "protocol",
                "name": "Entraînement par intervalles",
                "sports": ["running", "cycling", "swimming"],
                "levels": ["intermediate", "advanced"],
            },
        ),
    ]


def get_exercise_documents() -> list[Document]:
    """Exercise database with variations and considerations."""
    return [
        Document(
            id="ex_footing_z2",
            content="""Footing en Zone 2 (Endurance Fondamentale):
            Description: Course à allure modérée permettant une conversation.
            
            Caractéristiques:
            - FC: 65-75% FCM (ou 60-70% FCR)
            - RPE: 3-4/10
            - Respiration: confortable, phrases complètes possibles
            - Durée typique: 40-90 minutes
            
            Bénéfices:
            - Développement aérobie de base
            - Oxydation des graisses
            - Récupération active
            - Faible stress mécanique
            
            Erreur fréquente: Aller trop vite ! 
            La majorité de l'entraînement (80%) devrait être en Z2.
            
            Contribution charge: faible-modérée
            Fréquence recommandée: 3-5×/semaine""",
            metadata={
                "type": "exercise",
                "name": "Footing Zone 2",
                "category": "endurance",
                "sports": ["running"],
                "levels": ["all"],
                "load_coefficient": 0.6,
            },
        ),
        Document(
            id="ex_tempo_run",
            content="""Course au tempo (seuil lactique):
            Description: Course soutenue à allure "inconfortablement confortable".
            
            Caractéristiques:
            - FC: 85-90% FCM (seuil lactique)
            - RPE: 6-7/10
            - Respiration: difficile, phrases courtes seulement
            - Allure: environ allure semi-marathon
            - Durée: 20-40 minutes
            
            Bénéfices:
            - Repousse le seuil lactique
            - Améliore l'économie de course
            - Prépare aux courses longues
            
            Structure type:
            - 15' échauffement progressif
            - 20-30' tempo continu
            - 10' retour au calme
            
            Contribution charge: haute
            Fréquence: 1×/semaine max
            
            Précaution: Éviter si ACWR > 1.2 ou TSB < -15""",
            metadata={
                "type": "exercise",
                "name": "Course tempo",
                "category": "threshold",
                "sports": ["running"],
                "levels": ["intermediate", "advanced"],
                "load_coefficient": 1.2,
            },
        ),
        Document(
            id="ex_long_run",
            content="""Sortie longue (Long Run):
            Description: Course longue durée à allure modérée.
            
            Caractéristiques:
            - FC: 65-75% FCM (Z2, parfois toucher Z3)
            - RPE: 4-5/10 au départ, 6-7/10 en fin
            - Durée: 90 min à 3h selon objectif
            - Allure: marathon +30-60 sec/km
            
            Bénéfices:
            - Adaptation cardiovasculaire
            - Résistance à la fatigue
            - Gestion énergétique
            - Renforcement mental
            
            Progression:
            - Débutant: 60-90 min
            - Intermédiaire: 90-120 min
            - Marathon: jusqu'à 2h30-3h
            
            Contribution charge: très haute
            Fréquence: 1×/semaine (week-end)
            
            Récupération nécessaire: 48-72h
            Impact ACWR: significatif, planifier en conséquence""",
            metadata={
                "type": "exercise",
                "name": "Sortie longue",
                "category": "endurance",
                "sports": ["running"],
                "levels": ["all"],
                "load_coefficient": 1.5,
            },
        ),
        Document(
            id="ex_strength_squat",
            content="""Back Squat (Squat arrière):
            Description: Exercice fondamental de force pour le bas du corps.
            
            Muscles ciblés: Quadriceps, fessiers, ischio-jambiers, core.
            
            Zones d'entraînement:
            - Endurance: 60-70% 1RM, 12-15 reps
            - Hypertrophie: 70-80% 1RM, 8-12 reps
            - Force: 80-90% 1RM, 4-6 reps
            - Force max: 90%+ 1RM, 1-3 reps
            
            INOL (Intensity Number of Lifts):
            - < 0.75: léger (récupération)
            - 0.75-1.0: optimal pour progression
            - 1.0-2.0: élevé, fatigue importante
            - > 2.0: très élevé, risque surentraînement
            
            Variations si douleur/fatigue:
            - Goblet squat (moins de charge lombaire)
            - Front squat (moins de charge lombaire)
            - Split squat (unilatéral)
            - Box squat (contrôle ROM)""",
            metadata={
                "type": "exercise",
                "name": "Back Squat",
                "category": "strength",
                "sports": ["strength_training", "all"],
                "levels": ["intermediate", "advanced"],
                "muscle_groups": ["quadriceps", "glutes", "hamstrings"],
            },
        ),
    ]


def seed_knowledge_base(kb: KnowledgeBase | None = None) -> dict[str, int]:
    """Seed the knowledge base with initial documents.

    Args:
        kb: Optional existing knowledge base, creates new one if None

    Returns:
        Dictionary with count of documents added per collection
    """
    if kb is None:
        kb = KnowledgeBase()

    stats = {}

    # Add scientific documents
    scientific_docs = get_scientific_documents()
    stats["scientific"] = kb.add_documents("scientific", scientific_docs)

    # Add protocol documents
    protocol_docs = get_protocol_documents()
    stats["protocols"] = kb.add_documents("protocols", protocol_docs)

    # Add exercise documents
    exercise_docs = get_exercise_documents()
    stats["exercises"] = kb.add_documents("exercises", exercise_docs)

    return stats


if __name__ == "__main__":
    import logging

    logging.basicConfig(level=logging.INFO)

    print("Seeding knowledge base...")
    stats = seed_knowledge_base()
    print(f"Done! Added documents: {stats}")
