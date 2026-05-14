package com.berat.legaltech.gateway.dto;

import java.util.List;

public record AnalyzeResponse(
        String soru,
        List<String> cikarilanKavramlar,
        List<String> bulunanMaddeNumaralari,
        String mutalaa
) {}
