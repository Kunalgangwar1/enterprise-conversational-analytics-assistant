"""Bounded LLM-guided traversal over explicit catalog metadata."""

import json
from collections.abc import Callable

from app.knowledge_catalog.exceptions import CatalogTraversalError
from app.knowledge_catalog.loader import CatalogHierarchy
from app.knowledge_catalog.models import (
    CatalogDocument,
    CatalogTraversalDecision,
    KnowledgeEvidence,
    RetrievalMethod,
    RetrievalResult,
)
from app.llm.base import LLMClient
from app.llm.models import LLMMessage, LLMRequest, LLMRole

_TRAVERSAL_SYSTEM_PROMPT = """You select relevant child nodes in a trusted catalog hierarchy.
Return only the structured child IDs and confidence. Select no more than the allowed branches.
Use only IDs presented in the user message. Do not provide reasoning."""


class HierarchicalCatalogRetriever:
    """Use structured LLM decisions to descend from the catalog root."""

    def __init__(
        self,
        *,
        hierarchy: CatalogHierarchy,
        llm_client_factory: Callable[[], LLMClient],
        max_depth: int,
        max_branches: int,
        min_confidence: float,
        top_k: int,
    ) -> None:
        self._hierarchy = hierarchy
        self._llm_client_factory = llm_client_factory
        self._max_depth = max_depth
        self._max_branches = max_branches
        self._min_confidence = min_confidence
        self._top_k = top_k

    def retrieve(self, safe_question: str) -> RetrievalResult:
        current = (self._hierarchy.document(self._hierarchy.root.id),)
        confidence = 1.0
        for _depth in range(self._max_depth):
            children = _unique_children(self._hierarchy, current)
            if not children:
                break
            decision = self._select_children(safe_question, children)
            valid_ids = {child.node.id for child in children}
            unknown = sorted(set(decision.selected_child_ids) - valid_ids)
            if unknown:
                raise CatalogTraversalError(
                    f"Hierarchy traversal selected unknown child IDs: {', '.join(unknown)}"
                )
            if decision.confidence < self._min_confidence or not decision.selected_child_ids:
                return RetrievalResult(
                    retrieval_method=RetrievalMethod.HIERARCHICAL,
                    sufficient=False,
                    confidence=decision.confidence,
                )
            confidence = min(confidence, decision.confidence)
            selected_ids = list(dict.fromkeys(decision.selected_child_ids))[: self._max_branches]
            selected_by_id = {child.node.id: child for child in children}
            current = tuple(selected_by_id[node_id] for node_id in selected_ids)
            leaves = tuple(document for document in current if not document.node.children)
            if leaves:
                return RetrievalResult(
                    evidence=tuple(
                        _document_evidence(document, rank)
                        for rank, document in enumerate(leaves[: self._top_k], start=1)
                    ),
                    retrieval_method=RetrievalMethod.HIERARCHICAL,
                    sufficient=True,
                    confidence=confidence,
                )
        return RetrievalResult(
            retrieval_method=RetrievalMethod.HIERARCHICAL,
            sufficient=False,
            confidence=confidence,
        )

    def _select_children(
        self, safe_question: str, children: tuple[CatalogDocument, ...]
    ) -> CatalogTraversalDecision:
        child_payload = [
            {
                "id": child.node.id,
                "title": child.node.title,
                "summary": child.node.summary,
                "node_type": child.node.node_type.value,
            }
            for child in children
        ]
        user_content = (
            f"Question:\n{safe_question}\n\n"
            f"Maximum branches: {self._max_branches}\n"
            f"Available child nodes:\n{json.dumps(child_payload, sort_keys=True)}"
        )
        return self._llm_client_factory().generate_structured(
            LLMRequest(
                messages=[
                    LLMMessage(role=LLMRole.SYSTEM, content=_TRAVERSAL_SYSTEM_PROMPT),
                    LLMMessage(role=LLMRole.USER, content=user_content),
                ],
                temperature=0,
            ),
            CatalogTraversalDecision,
        )


def _unique_children(
    hierarchy: CatalogHierarchy, current: tuple[CatalogDocument, ...]
) -> tuple[CatalogDocument, ...]:
    by_id: dict[str, CatalogDocument] = {}
    for document in current:
        for child in hierarchy.children(document.node.id):
            by_id.setdefault(child.node.id, child)
    return tuple(by_id.values())


def _document_evidence(document: CatalogDocument, rank: int) -> KnowledgeEvidence:
    return KnowledgeEvidence(
        evidence_id=document.node.id,
        node_id=document.node.id,
        title=document.node.title,
        section="Document",
        source_path=document.node.source_path,
        text=document.text,
        retrieval_method=RetrievalMethod.HIERARCHICAL,
        rank=rank,
    )
