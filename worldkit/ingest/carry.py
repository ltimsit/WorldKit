"""Report des propositions d'ingestion à la fin d'un rejeu rétroactif (§6.4, décision J7 ; T-ING-16, R-PRI-04).

Le noyau (`worldkit.core.workflows.replay`) ne connaît pas les propositions : l'ingestion s'enregistre
comme reporteur. Chaque proposition en attente sur la branche remplacée est **déplacée** vers la nouvelle
branche (T-ING-16 : copie requalifiée contre la tête, originale close) ; la mémoire des décisions
(refus, abandons) est recopiée, pour qu'une ré-ingestion ne repose pas une question déjà tranchée (R-PRI-04).
"""

from __future__ import annotations

from worldkit.core.workflows.replay import CARRIERS, Carry
from worldkit.core.world import World


def carry_proposals(world: World, c: Carry) -> list[str]:
    from worldkit.ingest import decide
    from worldkit.ingest.queue import load
    from worldkit.ingest.store import ensure_tables
    ensure_tables(world.store.conn)
    source, target = c.replay.source, c.replay.branch
    handled = []
    for p in load(world, source):
        decide.move(world, p.id, target, reason=f"rejeu {c.replay.id}")
        handled.append(p.id)  # déplacée, ou bloquée (document obsolète) : elle reste tracée sur la source
    conn = world.store.conn
    with conn:
        conn.execute("INSERT INTO decisions (fingerprint, doc_id, passage_fp, branch_id, action, proposal, edit_id,"
                     " reason) SELECT fingerprint, doc_id, passage_fp, ?, action, proposal, edit_id, reason"
                     " FROM decisions WHERE branch_id = ? ORDER BY decision_id", (target, source))
    return handled


if carry_proposals not in CARRIERS:
    CARRIERS.append(carry_proposals)
