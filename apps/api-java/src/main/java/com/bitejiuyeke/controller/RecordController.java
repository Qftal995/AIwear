package com.bitejiuyeke.controller;

import com.bitejiuyeke.common.Result;
import com.bitejiuyeke.entity.Record;
import com.bitejiuyeke.log.ApiLog;
import com.bitejiuyeke.service.RecordService;
import jakarta.servlet.http.HttpServletRequest;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.*;

import java.util.List;

@Slf4j
@RestController
@RequestMapping("/api/record")
public class RecordController {

    @Autowired
    private RecordService recordService;

    @ApiLog
    @GetMapping("/my")
    public Result<List<Record>> my(
            HttpServletRequest request,
            @RequestParam(value = "action", required = false) String action
    ) {
        Long userId = (Long) request.getAttribute("userId");
        return Result.success("查询成功", recordService.my(userId, action));
    }
}
