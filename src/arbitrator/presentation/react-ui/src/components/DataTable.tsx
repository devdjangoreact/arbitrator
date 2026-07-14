// ponytail: generic table matching legacy HTML structure exactly. No complex sorting/pagination yet.
import React from "react";

export interface Column<T> {
  header: string;
  accessor: (row: T) => React.ReactNode;
  align?: "left" | "right" | "center";
}

interface DataTableProps<T> {
  data: T[];
  columns: Column<T>[];
  keyExtractor: (row: T) => string;
  emptyMessage?: string;
}

export function DataTable<T>({
  data,
  columns,
  keyExtractor,
  emptyMessage = "No data available",
}: DataTableProps<T>) {
  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            {columns.map((col, i) => (
              <th key={i} style={{ textAlign: col.align || "left" }}>
                {col.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {!Array.isArray(data) || data.length === 0 ? (
            <tr className="empty-row">
              <td colSpan={columns.length}>{emptyMessage}</td>
            </tr>
          ) : (
            (Array.isArray(data) ? data : []).map((row) => (
              <tr key={keyExtractor(row)}>
                {columns.map((col, i) => (
                  <td
                    key={i}
                    className={col.align === "right" ? "num" : ""}
                    style={{ textAlign: col.align || "left" }}
                  >
                    {col.accessor(row)}
                  </td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}
