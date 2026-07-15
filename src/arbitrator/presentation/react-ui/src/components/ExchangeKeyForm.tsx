import React, { useState } from "react";
import type { ExchangeConfig, SaveExchangePayload } from "../types";

interface Props {
  exchange: ExchangeConfig;
  onSave: (payload: SaveExchangePayload) => void;
}

export const ExchangeKeyForm: React.FC<Props> = ({ exchange, onSave }) => {
  const [apiKey, setApiKey] = useState(exchange.api_key_masked || "");
  const [apiSecret, setApiSecret] = useState("");
  const [apiPassword, setApiPassword] = useState("");

  const configuredText = exchange.configured ? " (налаштовано)" : "";

  const handleSave = () => {
    onSave({
      exchange_id: exchange.exchange_id,
      api_key: apiKey,
      api_secret: apiSecret,
      api_password: apiPassword,
    });
  };

  return (
    <div className="field" data-exchange-id={exchange.exchange_id}>
      <label>
        {exchange.exchange_id.toUpperCase()} API key{configuredText}
      </label>
      <input
        type="text"
        value={apiKey}
        onChange={(e) => setApiKey(e.target.value)}
        data-role="api-key"
        autoComplete="off"
        className="border border-gray-300 rounded px-2 py-1 mb-1 block w-full max-w-sm"
      />
      <input
        type="password"
        placeholder="API secret"
        value={apiSecret}
        onChange={(e) => setApiSecret(e.target.value)}
        data-role="api-secret"
        autoComplete="off"
        className="border border-gray-300 rounded px-2 py-1 mb-1 block w-full max-w-sm"
      />
      {exchange.has_password && (
        <input
          type="password"
          placeholder="API password"
          value={apiPassword}
          onChange={(e) => setApiPassword(e.target.value)}
          data-role="api-password"
          autoComplete="off"
          className="border border-gray-300 rounded px-2 py-1 mb-1 block w-full max-w-sm"
        />
      )}
      <button
        type="button"
        className="btn bg-blue-500 hover:bg-blue-600 text-white font-bold py-1 px-4 rounded mt-2"
        data-action="save"
        onClick={handleSave}
      >
        Зберегти
      </button>
    </div>
  );
};
