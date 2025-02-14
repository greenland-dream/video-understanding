from funasr import AutoModel
from funasr.utils.postprocess_utils import rich_transcription_postprocess
import torch
from pathlib import Path
from utils.log_config import setup_logger

logger = setup_logger(__name__)

class SenseVoiceTranscriber:
    def __init__(self, model_dir="iic/SenseVoiceSmall"):
        """
        Initialize SenseVoice transcriber
        
        Args:
            model_dir: Model directory or huggingface model name
        """
        try:
            # Detect device
            if torch.backends.mps.is_available():
                device = "mps"
                logger.info("Using MPS acceleration")
            elif torch.cuda.is_available():
                device = "cuda:0"
                logger.info("Using CUDA acceleration")
            else:
                device = "cpu"
                logger.info("Using CPU processing")
            
            logger.info(f"Loading SenseVoice model (model={model_dir}, device={device})")
            self.model = AutoModel(
                model=model_dir,
                trust_remote_code=True,
                remote_code="./model.py",
                vad_model="fsmn-vad",
                disable_update=True,
                vad_kwargs={
                    "max_single_segment_time": 15000,
                    "min_duration": 500,
                    "speech_pad": 300
                },
                device=device
            )
            
            logger.info("SenseVoice model loaded successfully")
            
        except Exception as e:
            logger.error(f"Failed to load SenseVoice model: {str(e)}")
            raise

    def transcribe(self, audio_path: str) -> str:
        """
        Transcribe audio to text
        
        Args:
            audio_path: Path to audio file
        Returns:
            str: Transcribed text or empty string if no speech detected
        """
        try:
            logger.info(f"Processing audio: {audio_path}")
            
            # Generate transcription with no gradient computation
            with torch.no_grad():
                res = self.model.generate(
                    input=audio_path,
                    cache={},
                    language="zh",
                    use_itn=True,
                    batch_size_s=30,
                    merge_vad=True,
                    merge_length_s=10,
                    ban_emo_unk=True
                )
            
            # Return empty string if no results
            if not res or not res[0].get("text"):
                logger.info("No speech detected")
                return ""
            
            # Get transcription text
            transcript = rich_transcription_postprocess(res[0]["text"])
            
            logger.info("Audio processing completed")
            logger.debug(f"Transcription result:\n{transcript}")
            
            return transcript
            
        except Exception as e:
            logger.error(f"Audio processing failed: {str(e)}")
            return ""  # Return empty string on error

