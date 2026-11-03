"""Regenerate synthetic fixtures (validated through the contracts).

Run: ``uv run python tests/fixtures/build_fixtures.py``. Every record is SYNTHETIC: part numbers start
with ``SYN-`` and the manufacturer is fictitious. They do not describe real products or statuses.
"""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from pathlib import Path

import networkx as nx

from advisor.models import (
    Category,
    CommercialInformation,
    CommercialStatus,
    CompatibilityLevel,
    CompatibilityResult,
    CustomerQuery,
    EdgeType,
    Evidence,
    GraphEdge,
    GraphNode,
    NodeType,
    Operator,
    ParsedQuery,
    Product,
    ProductSpecification,
    Recommendation,
    RecommendationResponse,
    RequirementOrigin,
    RuleOutcome,
    RuleResult,
    Severity,
    TechnicalRequirement,
)

HERE = Path(__file__).parent
MAKER = "Synthetic Labs (fictitious)"


def doc_id(name: str) -> str:
    return hashlib.sha256(f"synthetic::{name}".encode()).hexdigest()


def ev(part: str, quote: str) -> Evidence:
    return Evidence(document_id=doc_id(part), page=1, chunk_id=f"{part}:1:0", quote=quote)


def spec(part: str, key: str, value: object, unit: str | None, quote: str) -> ProductSpecification:
    return ProductSpecification(key=key, value=value, unit=unit, evidence=[ev(part, quote)])  # type: ignore[arg-type]


def commercial(
    part: str, desc: str, cat: Category, status: CommercialStatus, price: str | None, stock: int
) -> CommercialInformation:
    return CommercialInformation(
        part_number=part,
        description=desc,
        manufacturer=MAKER,
        category=cat,
        status=status,
        price_usd=Decimal(price) if price else None,
        stock_units=stock,
    )


def products() -> list[Product]:
    rows = [
        (
            "SYN-NIC-100",
            Category.NETWORK,
            "Synthetic 100GbE NIC",
            CommercialStatus.DISCONTINUED,
            None,
            0,
            [
                ("port_speed", 100, "Gb/s", "Port speed: 2x 100GbE"),
                ("rdma", ["RoCE v2"], None, "RDMA: RoCE v2"),
                ("offloads", ["IPsec", "VXLAN"], None, "Offloads: IPsec, VXLAN"),
                ("host_interface", "PCIe 4.0 x16", None, "Host: PCIe 4.0 x16"),
            ],
        ),
        (
            "SYN-NIC-200",
            Category.NETWORK,
            "Synthetic 200GbE NIC",
            CommercialStatus.ACTIVE,
            "900.00",
            40,
            [
                ("port_speed", 200, "Gb/s", "Port speed: 2x 200GbE"),
                ("rdma", ["RoCE v2"], None, "RDMA: RoCE v2"),
                ("offloads", ["IPsec", "TLS", "VXLAN"], None, "Offloads: IPsec, TLS, VXLAN"),
                (
                    "host_interface",
                    "PCIe 5.0 x16",
                    None,
                    "Host: PCIe 5.0 x16 (backward compatible)",
                ),
            ],
        ),
        (
            "SYN-GPU-100",
            Category.GPU,
            "Synthetic 80GB accelerator",
            CommercialStatus.NRND,
            None,
            5,
            [
                ("memory_size", 80, "GB", "Memory: 80 GB"),
                ("form_factor", "SXM", None, "Form factor: SXM"),
            ],
        ),
        (
            "SYN-GPU-200",
            Category.GPU,
            "Synthetic 96GB accelerator",
            CommercialStatus.ACTIVE,
            "2500.00",
            12,
            [
                ("memory_size", 96, "GB", "Memory: 96 GB"),
                ("form_factor", "SXM", None, "Form factor: SXM"),
            ],
        ),
        (
            "SYN-DAQ-100",
            Category.DAQ,
            "Synthetic USB DAQ",
            CommercialStatus.EOL,
            None,
            0,
            [
                ("analog_inputs", 16, "count", "16 analog inputs"),
                ("resolution", 16, "bit", "Resolution: 16 bits"),
                ("host_interface", "USB 2.0", None, "Interface: USB 2.0"),
            ],
        ),
        (
            "SYN-MCU-100",
            Category.MICROCONTROLLER,
            "Synthetic Cortex-M MCU",
            CommercialStatus.ACTIVE,
            "4.50",
            10000,
            [("flash", 512, "KB", "Flash: 512 KB"), ("sram", 128, "KB", "SRAM: 128 KB")],
        ),
    ]
    return [
        Product(
            part_number=part,
            manufacturer=MAKER,
            category=cat,
            description=desc,
            specifications=[spec(part, *s) for s in specs],
            commercial=commercial(part, desc, cat, status, price, stock),
            document_ids=[doc_id(part)],
            is_synthetic=True,
        )
        for part, cat, desc, status, price, stock, specs in rows
    ]


def graph(items: list[Product]) -> nx.MultiDiGraph:
    g = nx.MultiDiGraph()
    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []
    for p in items:
        pid = f"product:{p.part_number}"
        nodes.append(GraphNode(node_id=pid, node_type=NodeType.PRODUCT, label=p.part_number))
        cid = f"category:{p.category.value}"
        nodes.append(GraphNode(node_id=cid, node_type=NodeType.CATEGORY, label=p.category.value))
        edges.append(GraphEdge(source=pid, target=cid, edge_type=EdgeType.IN_CATEGORY))
        assert p.commercial is not None
        sid = f"status:{p.commercial.status.value}"
        nodes.append(GraphNode(node_id=sid, node_type=NodeType.STATUS, label=sid.split(":")[1]))
        edges.append(GraphEdge(source=pid, target=sid, edge_type=EdgeType.HAS_STATUS))
        for s in p.specifications:
            if s.key in ("rdma", "offloads") and isinstance(s.value, list):
                for proto in s.value:
                    nid = f"protocol:{proto}"
                    nodes.append(GraphNode(node_id=nid, node_type=NodeType.PROTOCOL, label=proto))
                    edges.append(
                        GraphEdge(
                            source=pid,
                            target=nid,
                            edge_type=EdgeType.SUPPORTS_PROTOCOL,
                            evidence=s.evidence,
                        )
                    )
    edges.append(
        GraphEdge(
            source="product:SYN-NIC-100",
            target="product:SYN-NIC-200",
            edge_type=EdgeType.SIMILAR_TO,
            weight=0.8,
        )
    )
    for n in nodes:
        g.add_node(n.node_id, **n.model_dump(mode="json", exclude={"node_id"}))
    for e in edges:
        g.add_edge(
            e.source,
            e.target,
            key=e.edge_type.value,
            **e.model_dump(mode="json", exclude={"source", "target"}),
        )
    return g


def responses(items: list[Product]) -> dict[str, RecommendationResponse]:
    by = {p.part_number: p for p in items}
    nic_req = [
        TechnicalRequirement(
            key="port_speed",
            operator=Operator.GTE,
            value=100,
            unit="Gb/s",
            origin=RequirementOrigin.QUERY,
        ),
        TechnicalRequirement(
            key="rdma", operator=Operator.HAS, value="RoCE v2", origin=RequirementOrigin.QUERY
        ),
        TechnicalRequirement(
            key="offloads", operator=Operator.HAS, value="IPsec", origin=RequirementOrigin.QUERY
        ),
    ]
    nic_q = "Necesito una NIC de 100 GbE con RDMA e IPsec offload. Usábamos la SYN-NIC-100."
    nic200 = by["SYN-NIC-200"]
    assert nic200.commercial is not None
    replacement = RecommendationResponse(
        query=CustomerQuery(text=nic_q, language="es"),
        parsed_query=ParsedQuery(
            original_text=nic_q,
            part_numbers=["SYN-NIC-100"],
            category=Category.NETWORK,
            requirements=nic_req,
        ),
        original=by["SYN-NIC-100"],
        recommendations=[
            Recommendation(
                rank=1,
                product=nic200,
                commercial=nic200.commercial,
                compatibility=CompatibilityResult(
                    original_part_number="SYN-NIC-100",
                    candidate_part_number="SYN-NIC-200",
                    level=CompatibilityLevel.COMPATIBLE_WITH_CONDITIONS,
                    rule_results=[
                        RuleResult(
                            rule_id="R-CAT",
                            severity=Severity.CRITICAL,
                            outcome=RuleOutcome.PASS,
                            message="Network = Network",
                        ),
                        RuleResult(
                            rule_id="R-MUST-PROTO",
                            severity=Severity.CRITICAL,
                            outcome=RuleOutcome.PASS,
                            message="RoCE v2 and IPsec present",
                            evidence=nic200.specifications[1].evidence,
                        ),
                        RuleResult(
                            rule_id="R-UPGRADE",
                            severity=Severity.MINOR,
                            outcome=RuleOutcome.CONDITIONAL,
                            message="200GbE ports; requires 200G-capable optics/switch or breakout",
                        ),
                    ],
                    coverage=1.0,
                    score=0.92,
                    conditions=[
                        "Validate optics/switch for 200GbE or use breakout",
                        "PCIe 5.0 card in PCIe 4.0 slot",
                    ],
                ),
                covered_requirements=[
                    "port_speed>=100 Gb/s",
                    "rdma HAS RoCE v2",
                    "offloads HAS IPsec",
                ],
                rationale="Same category, all mandatory protocols present, higher port speed (conditional upgrade).",
                evidence=[e for s in nic200.specifications for e in s.evidence],
            )
        ],
        message="SYN-NIC-100 está DISCONTINUED. Sustituto activo: SYN-NIC-200 (900.00 USD, 40 unidades).",
        is_synthetic=True,
    )
    vague_q = "Necesito un reemplazo para la tarjeta"
    clarification = RecommendationResponse(
        query=CustomerQuery(text=vague_q, language="es"),
        parsed_query=ParsedQuery(
            original_text=vague_q,
            needs_clarification=True,
            clarification_question="¿Qué part number o categoría?",
        ),
        clarification_question="¿Qué part number o categoría de producto necesitas reemplazar?",
        message="Necesito más información para buscar un sustituto.",
        is_synthetic=True,
    )
    daq_q = "Reemplazo para SYN-DAQ-100"
    no_substitute = RecommendationResponse(
        query=CustomerQuery(text=daq_q, language="es"),
        parsed_query=ParsedQuery(
            original_text=daq_q, part_numbers=["SYN-DAQ-100"], category=Category.DAQ
        ),
        original=by["SYN-DAQ-100"],
        message="SYN-DAQ-100 está EOL y no hay sustituto ACTIVE compatible en el catálogo.",
        warnings=["No ACTIVE product in category DAQ"],
        is_synthetic=True,
    )
    return {
        "replacement_found": replacement,
        "clarification": clarification,
        "no_substitute": no_substitute,
    }


def dump(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> None:
    items = products()
    dump(HERE / "products.json", [p.model_dump(mode="json") for p in items])
    dump(
        HERE / "commercial.json",
        [p.commercial.model_dump(mode="json") for p in items if p.commercial],
    )
    dump(HERE / "mock_graph.json", nx.node_link_data(graph(items), edges="edges"))
    out = HERE / "responses"
    out.mkdir(exist_ok=True)
    for name, resp in responses(items).items():
        dump(out / f"{name}.json", resp.model_dump(mode="json"))


if __name__ == "__main__":
    main()
