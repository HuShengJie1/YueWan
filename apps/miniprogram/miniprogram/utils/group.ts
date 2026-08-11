const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function isValidUuid(value: string): boolean {
  return UUID_PATTERN.test(value);
}

export function isValidGroupId(groupId: string): boolean {
  return isValidUuid(groupId);
}
