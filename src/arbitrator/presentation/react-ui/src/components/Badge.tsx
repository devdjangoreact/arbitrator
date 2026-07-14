// ponytail: wrapper for the legacy status-badge classes
export function Badge({
  children,
  variant = "closed",
}: {
  children: React.ReactNode;
  variant?: "open" | "closed" | "short" | "long";
}) {
  // Use the legacy CSS classes directly
  const baseClass =
    variant === "short" || variant === "long" ? "badge" : "status-badge";
  return <span className={`${baseClass} ${variant}`}>{children}</span>;
}
