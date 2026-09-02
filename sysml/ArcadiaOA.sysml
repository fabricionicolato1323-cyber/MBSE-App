// ArcadiaOA is the normative SysML v2 semantic library for OA translation.
// ArcadiaOA.translation.json is part of this library bundle and is the sole
// machine-readable authority for translating source OA concepts and relations.
// The generator must not invent semantic mappings or generic fallbacks.
//
// Translation semantics intentionally use native SysML v2 constructs:
// - structural and behavioral decomposition/composition -> nested usages;
// - physical/operational LOCATED_IN -> non-composite ref part usage;
// - Operational Capability support by Operational Activity -> allocation usage;
// - Operational Exchange -> flow;
// - Communication Mean -> connection.

package ArcadiaOA {
    part def OperationalEntity;
    part def OperationalActor :> OperationalEntity;

    action def OperationalActivity;
    item def OperationalInformation;

    flow def OperationalExchange;
    connection def CommunicationMean;

    action def OperationalScenario;
    requirement def OperationalCapability;
}
