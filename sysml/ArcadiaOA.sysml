// ArcadiaOA is the normative SysML v2 semantic library for OA translation.
// ArcadiaOA.translation.json is part of this library bundle and is the sole
// machine-readable authority for translating source OA concepts and relations.
// The generator must not invent semantic mappings or generic fallbacks.

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
