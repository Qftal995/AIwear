package com.bitejiuyeke.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.bitejiuyeke.dto.request.EditImageRequest;
import com.bitejiuyeke.dto.request.MergeImageRequest;
import com.bitejiuyeke.dto.response.EditImageResponse;
import com.bitejiuyeke.dto.response.MergeImageResponse;
import com.bitejiuyeke.entity.Record;
import com.bitejiuyeke.mapper.RecordMapper;
import com.bitejiuyeke.service.RecordService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

import java.util.List;

// 历史记录的实现类
@Service
public class RecordServiceImpl implements RecordService {

    @Autowired
    private RecordMapper recordMapper;

    @Override
    public List<Record> my(Long userId, String action) {
        LambdaQueryWrapper<Record> queryWrapper = new LambdaQueryWrapper<>();
        queryWrapper.eq(Record::getUserId, userId);
        if (action != null && !action.isBlank()) {
            queryWrapper.eq(Record::getAction, action);
        }
        queryWrapper.orderByDesc(Record::getId);
        return recordMapper.selectList(queryWrapper);
    }

    @Override
    public void editSave(Long userId, EditImageRequest editImageRequest, EditImageResponse editImageResponse) {
        Record record = new Record();
        record.setUserId(userId);
        record.setAction("edit");
        record.setInputOssUrl1(editImageRequest.getImage());
        record.setInstruction(editImageRequest.getInstruction());
        record.setResultUrl(editImageResponse.getUrl());
        record.setOutputOssUrl(editImageResponse.getSaveUrl());
        recordMapper.insert(record);
    }

    @Override
    public void mergeSave(Long userId, MergeImageRequest mergeImageRequest, MergeImageResponse mergeImageResponse) {
        Record record = new Record();
        record.setUserId(userId);
        record.setAction("merge");
        record.setInputOssUrl1(mergeImageRequest.getImage1());
        record.setInputOssUrl2(mergeImageRequest.getImage2());
        record.setInstruction(mergeImageRequest.getInstruction());
        record.setResultUrl(mergeImageResponse.getUrl());
        record.setOutputOssUrl(mergeImageResponse.getSaveUrl());
        recordMapper.insert(record);
    }
}
