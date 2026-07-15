import React, { useState, useEffect } from "react";

interface Props {
  value: any;
  onChange: (value: any) => void;
  className?: string;
}

export const JsonEditorTextarea: React.FC<Props> = ({
  value,
  onChange,
  className,
}) => {
  const [textValue, setTextValue] = useState("");
  const [error, setError] = useState<string | null>(null);

  // Sync prop value to text state when it changes from outside
  useEffect(() => {
    setTextValue(JSON.stringify(value, null, 2));
  }, [value]);

  const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const newText = e.target.value;
    setTextValue(newText);

    try {
      const parsed = JSON.parse(newText);
      setError(null);
      onChange(parsed);
    } catch (err) {
      setError((err as Error).message);
    }
  };

  return (
    <div className={`w-full ${className || ""}`}>
      <textarea
        value={textValue}
        onChange={handleChange}
        className={`w-full h-48 font-mono text-sm border p-2 rounded ${error ? "border-red-500" : "border-gray-300"}`}
        spellCheck="false"
      />
      {error && (
        <div className="text-red-500 text-xs mt-1">Invalid JSON: {error}</div>
      )}
    </div>
  );
};
