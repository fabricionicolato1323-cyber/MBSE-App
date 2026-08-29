function revisionCharacteristicOperatorSymbol(operator) {
  return ({
    '=': '=',
    '>': '>',
    '>=': '≥',
    '≥': '≥',
    '<': '<',
    '<=': '≤',
    '≤': '≤'
  })[operator] || operator || '=';
}

function revisionOperatorAwareCharacteristicText(characteristic) {
  const name = characteristic.name || 'Characteristic';
  const unit = characteristic.unit ? ` ${characteristic.unit}` : '';

  if (characteristic.value_type === 'range' ||
      characteristic.lower_bound !== undefined ||
      characteristic.upper_bound !== undefined) {
    const lower = characteristic.lower_bound ?? '';
    const upper = characteristic.upper_bound ?? '';
    const lowerOperator = characteristic.lower_operator || '>=';
    const upperOperator = characteristic.upper_operator || '<=';
    const lowerRelation = lowerOperator === '>' ? '<' : '≤';
    const upperRelation = upperOperator === '<' ? '<' : '≤';
    return `${name}: ${lower} ${lowerRelation} value ${upperRelation} ${upper}${unit}`;
  }

  if (characteristic.value_type === 'number' ||
      typeof characteristic.value === 'number') {
    const symbol = revisionCharacteristicOperatorSymbol(characteristic.operator || '=');
    return `${name}: ${symbol} ${characteristic.value ?? ''}${unit}`;
  }

  const value = characteristic.value ?? '';
  return value !== '' ? `${name}: ${value}` : name;
}

// revision_model.js defines the common renderer first. Replace only the
// characteristic text formatter so both Textual and Details views use the
// operator-aware representation without duplicating the rest of the model UI.
revisionCharacteristicText = revisionOperatorAwareCharacteristicText;
