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
