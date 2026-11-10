type PlaceholderPageProps = {
  title: string;
};

export function PlaceholderPage({ title }: PlaceholderPageProps) {
  return (
    <div className="placeholder-note">
      <p style={{ margin: "0 0 0.5rem", fontWeight: 600 }}>{title}</p>
      <p style={{ margin: 0 }} className="muted">
        鱼咖小哥还在砌这一格～很快能用的。
      </p>
    </div>
  );
}
