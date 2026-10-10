---
name: document-planning
description: Retrouver et interpréter une semaine d’entraînement dans un document joint, notamment un tableur, avant de préparer son import.
---

# Lire un planning joint

1. Repère le chemin du document dans le contexte et la période demandée. Pour
   une semaine relative, calcule d’abord ses dates depuis la date actuelle fournie.
2. Recherche les dates dans le document avec `grep` (texte littéral). Les dates
   calculées d’un tableur figurent parfois dans une « valeur enregistrée » ISO.
   Une recherche vide sur « octobre » ne prouve pas que la semaine manque.
3. Lis le bloc de lignes autour du résultat avec `read_file`. Son `offset` est
   indexé à zéro et son `limit` est compris entre 1 et 200. Pour poursuivre,
   avance l’offset du nombre de lignes déjà reçues. Ne demande pas tout le fichier
   par défaut et ne relis pas un bloc déjà présent dans l’échange.
4. Dans un tableur, utilise les références feuille/cellule pour relier les dates
   et les séances de la même colonne. Une séance peut continuer sur plusieurs
   lignes : lis aussi les lignes suivantes, jusqu’au prochain bloc de dates.
   Conserve les formules et leurs valeurs enregistrées comme preuves distinctes.
5. Assemble les séances de la période avec leurs références de source. Une
   cellule vide ne permet pas d’inventer une séance. Si les données indispensables
   manquent, indique précisément lesquelles et où la lecture s’arrête.
6. Suis les règles du toolkit planning pour préparer l’import et présenter son
   aperçu. Distingue toujours ce qui a été lu, proposé et réellement enregistré.

Ce skill décrit une méthode ; il n’accorde aucun outil ni aucune permission.
