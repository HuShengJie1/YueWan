export interface CursorPage<T> {
  items: T[];
  next_cursor: string | null;
  has_more: boolean;
}
